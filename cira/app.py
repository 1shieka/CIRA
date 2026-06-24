"""
Cyber First Response Officer (CFRO)
AI Case Officer Workspace entry point.
"""

import json
import datetime
from pathlib import Path
import streamlit as st

# Import Components
from components.emergency_actions import render_emergency_actions
from components.response_guide import render_response_guide
from components.complaint_package_exports import (
    render_complaint_package_exports,
    generate_complaint_package_text,
    generate_printable_summary_html,
)
from components.threat_intelligence import render_threat_intelligence
from components.evidence_checklist import EVIDENCE_BY_CATEGORY, GENERIC_EVIDENCE

# Import Utilities
from utils.classification_mapper import (
    get_all_subcategories,
    get_subcategory_names,
    map_to_official_category,
)
from utils.llm_client import generate_summary_and_timeline, understand_incident
from utils.azure_openai_client import call_azure_openai
from utils.rule_engine import get_followup_questions
from utils.pdf_generator import generate_pdf_report
from utils.playbook_loader import load_playbook
from agent import (
    call_agent,
    call_verifier,
    load_agent_prompt,
    load_evaluation_matrix,
    load_verifier_prompt,
)

# --- Session State Configuration ---
DEFAULT_SESSION = {
    "messages": [],  # List of dicts: {"role": "assistant"|"user", "content": str, "type": "text"|"quick_reply"|"evidence_checklist", "options": list, "checked": dict}
    "case_data": {},
    "classification": None,
    "timeline": [],
    "summary": "",
    "evidence": {},
    "followup_answers": {},
    "playbook": None,
    # Internal state machine
    "stage": "stage_1_intake",
    "incident_description": "",
    "ai_understanding": None,
    "remaining_questions": [],
    "summary_generated": False,
}

def init_session():
    """Initialize session state keys."""
    for key, val in DEFAULT_SESSION.items():
        if key not in st.session_state:
            st.session_state[key] = val
            
    # Open the conversation with Stage 1 intro if empty
    if not st.session_state.messages:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Hello. I'm here to help. Please describe what happened in your own words.",
            "type": "text"
        })

def reset_session():
    """Wipe session state to start a new case."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session()
    st.rerun()

def load_categories_meta() -> dict:
    path = Path(__file__).parent / "data" / "categories.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# --- Metadata Lookup Helpers ---
def get_evidence_items(category_id: str | None) -> list[dict]:
    """Get all evidence items for a given category."""
    if not category_id:
        category_id = "other-categories"
    items = EVIDENCE_BY_CATEGORY.get(category_id, EVIDENCE_BY_CATEGORY.get("other-categories", []))
    return items + GENERIC_EVIDENCE

def get_evidence_labels_map(category_id: str | None) -> dict[str, str]:
    """Compile a mapping of evidence ID to label string."""
    items = get_evidence_items(category_id)
    return {item["id"]: item["label"] for item in items}

def get_questions_labels_map() -> dict[str, str]:
    """Compile a mapping of all question IDs to their prompt texts."""
    from utils.rule_engine import GENERIC_QUESTIONS, CATEGORY_SPECIFIC_QUESTIONS, SUBCATEGORY_SPECIFIC_QUESTIONS
    labels = {}
    for q in GENERIC_QUESTIONS:
        labels[q["id"]] = q["text"]
    for q_list in CATEGORY_SPECIFIC_QUESTIONS.values():
        for q in q_list:
            labels[q["id"]] = q["text"]
    for q_list in SUBCATEGORY_SPECIFIC_QUESTIONS.values():
        for q in q_list:
            labels[q["id"]] = q["text"]
    return labels

# --- AI Helper Triggers ---
def trigger_ai_summary_timeline():
    """Trigger the LLM call to generate the case summary and timeline."""
    case_data = {
        "incident_description": st.session_state.incident_description,
        "classification": st.session_state.classification,
        "followup_answers": st.session_state.followup_answers,
        "evidence_collected": st.session_state.evidence,
        "ai_understanding": st.session_state.ai_understanding,
    }
    result = generate_summary_and_timeline(case_data)
    if "error" not in result:
        st.session_state.summary = result.get("summary", "")
        st.session_state.timeline = result.get("timeline", [])
        st.session_state.summary_generated = True

def handle_category_select(subcategory_id: str):
    """Set classification when manually chosen or confirmed."""
    meta = load_categories_meta()
    selected_sub = next(s for s in meta["subcategories"] if s["id"] == subcategory_id)
    selected_cat = next(c for c in meta["categories"] if c["id"] == selected_sub["category_id"])

    st.session_state.classification = {
        "category_id": selected_sub["category_id"],
        "category_name": selected_cat["name"],
        "subcategory_id": selected_sub["id"],
        "subcategory_name": selected_sub["name"],
        "match_confidence": 1.0,
        "needs_confirmation": False,
    }
    
    from utils.playbook_loader import load_playbook
    st.session_state.playbook = load_playbook(subcategory_id)
    
    # Load followups
    st.session_state.remaining_questions = get_followup_questions(subcategory_id, st.session_state.followup_answers)
    
    # Generate initial summary/timeline
    trigger_ai_summary_timeline()

# --- Main App Orchestration ---
def legacy_workspace():
    st.set_page_config(
        page_title="CFRO — Cyber First Response Officer",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    init_session()

    # ── Global CSS: conversation-first workspace ──────────────────────────────
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700&display=swap');

        /* ── Reset Streamlit chrome ─────────────────────────── */
        .block-container {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
            max-width: 100% !important;
        }
        section.main > div { padding-top: 0 !important; }
        header[data-testid="stHeader"] { display: none !important; }
        .element-container { margin-bottom: 0 !important; }
        footer { display: none !important; }

        /* ── Base ───────────────────────────────────────────── */
        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Inter', sans-serif !important;
            background-color: #F0F2F5 !important;
            color: #1A202C !important;
        }
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Outfit', sans-serif !important;
            color: #111827 !important;
            margin: 0 0 6px 0 !important;
            font-size: inherit !important;
            font-weight: inherit !important;
            line-height: inherit !important;
        }

        /* ── Top command bar ────────────────────────────────── */
        div[data-element-id="top_header_container"] {
            background-color: #FFFFFF !important;
            padding: 10px 24px !important;
            border-bottom: 1px solid #E5E7EB !important;
            margin-bottom: 12px !important;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06) !important;
        }
        div[data-element-id="top_header_container"] div[data-testid="stHorizontalBlock"] {
            align-items: center !important;
            gap: 12px !important;
        }
        div[data-element-id="top_header_container"] button {
            margin: 0 !important;
            height: 36px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 0.83rem !important;
            font-weight: 600 !important;
        }
        div[data-element-id="top_header_container"] button[data-testid="baseButton-primary"] {
            background-color: #2563EB !important;
            color: white !important;
            border: 1px solid #2563EB !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 3px rgba(37,99,235,0.3) !important;
        }
        div[data-element-id="top_header_container"] button[data-testid="baseButton-primary"]:hover {
            background-color: #1D4ED8 !important;
            border-color: #1D4ED8 !important;
        }
        div[data-element-id="top_header_container"] button[data-testid="baseButton-secondary"] {
            background-color: #F9FAFB !important;
            color: #374151 !important;
            border: 1px solid #D1D5DB !important;
            border-radius: 8px !important;
        }
        div[data-element-id="top_header_container"] button[data-testid="baseButton-secondary"]:hover {
            background-color: #F3F4F6 !important;
            border-color: #9CA3AF !important;
        }


        /* ── LEFT SIDEBAR (light, matching reference) ─────────── */
        div[data-element-id="left_sidebar_container"] {
            background-color: #F0F2F5 !important;
            color: #111827 !important;
            padding: 16px 14px !important;
            border-radius: 12px !important;
            box-shadow: none !important;
            min-height: calc(100vh - 110px) !important;
        }


        /* ── Header title area ──────────────────────────────── */
        .cmd-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.05rem;
            font-weight: 700;
            color: #111827 !important;
            letter-spacing: -0.2px;
        }
        .cmd-subtitle {
            font-size: 0.67rem;
            color: #6B7280 !important;
            margin-top: 1px;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            font-weight: 500;
        }
        .cmd-badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            background: #F0FDF4 !important;
            border: 1px solid #BBF7D0 !important;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.7rem;
            color: #15803D !important;
            font-weight: 600;
        }
        .live-dot {
            width: 7px; height: 7px;
            background: #22C55E !important;
            border-radius: 50%;
            animation: pulse-dot 2s ease-in-out infinite;
        }
        @keyframes pulse-dot {
            0%, 100% { box-shadow: 0 0 0 0 rgba(34,197,94,0.4); }
            50% { box-shadow: 0 0 0 4px rgba(34,197,94,0); }
        }

        /* ── CHAT PANEL ─────────────────────────────────────── */
        div[data-testid="stColumn"]:has([data-testid="stChatMessage"]) > div[data-testid="stVerticalBlock"] {
            background: #FFFFFF !important;
            border: 1px solid #E5E7EB !important;
            border-radius: 14px !important;
            box-shadow: 0 2px 16px rgba(0,0,0,0.07) !important;
            overflow: hidden !important;
            padding-top: 0 !important;
        }
        div[data-testid="stColumn"]:has([data-testid="stChatMessage"]) [data-testid="stBottom"] {
            background: #FFFFFF !important;
            border-top: 1px solid #F3F4F6 !important;
            padding: 10px 16px 10px !important;
        }

        /* Chat panel header strip */
        .chat-panel-hdr {
            background: linear-gradient(90deg, #1E3A5F 0%, #1E4976 100%);
            padding: 10px 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 4px;
        }
        .chat-panel-hdr-title {
            font-family: 'Outfit', sans-serif;
            font-size: 0.87rem;
            font-weight: 700;
            color: #FFFFFF;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .chat-panel-hdr-stage {
            font-size: 0.72rem;
            color: #93C5FD;
            font-weight: 400;
        }

        /* ── Chat bubbles ───────────────────────────────────── */
        div[data-testid="stChatMessage"] {
            padding: 8px 16px !important;
        }
        /* Assistant bubble */
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"] {
            background: #F8FAFC !important;
            border-radius: 2px 14px 14px 14px !important;
            padding: 12px 16px !important;
            border: 1px solid #E9ECF0 !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
        }
        /* User bubble */
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] {
            background: #EFF6FF !important;
            border-radius: 14px 2px 14px 14px !important;
            padding: 12px 16px !important;
            border: 1px solid #DBEAFE !important;
            box-shadow: 0 1px 3px rgba(37,99,235,0.06) !important;
        }
        div[data-testid="chatAvatarIcon-assistant"] > div {
            background: #1E3A5F !important;
            border-radius: 50% !important;
        }
        div[data-testid="chatAvatarIcon-user"] > div {
            background: #2563EB !important;
            border-radius: 50% !important;
        }
        div[data-testid="stChatMessageContent"] p {
            font-size: 0.9rem !important;
            line-height: 1.7 !important;
            color: #1F2937 !important;
            margin: 0 !important;
        }

        /* Chat input */
        div[data-testid="stChatInput"] {
            border: 1.5px solid #D1D5DB !important;
            border-radius: 10px !important;
            background: #FAFAFA !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
        }
        div[data-testid="stChatInput"]:focus-within {
            border-color: #2563EB !important;
            box-shadow: 0 0 0 3px rgba(37,99,235,0.1) !important;
        }
        div[data-testid="stChatInput"] textarea {
            font-size: 0.9rem !important;
            color: #1F2937 !important;
            background: transparent !important;
        }

        /* ── Right panel cards ──────────────────────────────── */
        .panel-card {
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 12px;
            padding: 14px 16px;
            margin-bottom: 12px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }
        .panel-label {
            font-family: 'Outfit', sans-serif;
            font-size: 0.72rem;
            font-weight: 700;
            color: #374151;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid #F3F4F6;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .section-header {
            font-family: 'Outfit', sans-serif;
            font-size: 0.82rem;
            font-weight: 700;
            color: #111827;
            margin-bottom: 8px;
            padding-bottom: 6px;
            border-bottom: 1px solid #F3F4F6;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        /* ── Quick-reply chips ──────────────────────────────── */
        div[data-testid="stButton"] > button {
            border-radius: 8px !important;
            font-size: 0.83rem !important;
            padding: 6px 14px !important;
        }

        /* ── Primary / Secondary buttons ────────────────────── */
        .stButton > button[data-testid="baseButton-primary"] {
            background: #2563EB !important;
            color: #FFF !important;
            border: 1px solid #2563EB !important;
            font-weight: 600 !important;
            border-radius: 8px !important;
        }
        .stButton > button[data-testid="baseButton-primary"]:hover {
            background: #1D4ED8 !important;
        }
        .stButton > button[data-testid="baseButton-secondary"] {
            background: #FFFFFF !important;
            color: #374151 !important;
            border: 1px solid #D1D5DB !important;
            border-radius: 8px !important;
        }
        .stButton > button[data-testid="baseButton-secondary"]:hover {
            background: #F9FAFB !important;
        }

        /* ── Download buttons ───────────────────────────────── */
        .stDownloadButton > button {
            background: #F9FAFB !important;
            color: #374151 !important;
            border: 1px solid #D1D5DB !important;
            border-radius: 8px !important;
            font-size: 0.81rem !important;
            font-weight: 500 !important;
            width: 100%;
            margin-bottom: 4px !important;
        }
        .stDownloadButton > button:hover {
            background: #F3F4F6 !important;
            border-color: #9CA3AF !important;
        }

        /* ── Native bordered container ──────────────────────── */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 10px !important;
            border-color: #E5E7EB !important;
        }

        /* ── Expanders ──────────────────────────────────────── */
        div[data-testid="stExpander"] {
            border: 1px solid #E5E7EB !important;
            border-radius: 8px !important;
            background: #FAFAFA !important;
            margin-bottom: 6px !important;
        }
        div[data-testid="stExpander"] summary {
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            color: #1F2937 !important;
            padding: 8px 12px !important;
        }

        /* ── Inputs ─────────────────────────────────────────── */
        textarea, input[type="text"] {
            border: 1px solid #D1D5DB !important;
            border-radius: 8px !important;
            background: #FFFFFF !important;
            color: #1F2937 !important;
            font-size: 0.86rem !important;
        }
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextArea"] label,
        div[data-testid="stSelectbox"] label {
            display: none !important;
        }

        /* ── Checkbox styling ───────────────────────────────── */
        div[data-testid="stCheckbox"] label {
            font-size: 0.84rem !important;
            color: #1F2937 !important;
        }

        /* ── Alerts ─────────────────────────────────────────── */
        div[data-testid="stAlert"] {
            padding: 8px 12px !important;
            font-size: 0.82rem !important;
            border-radius: 8px !important;
        }

        /* ── Divider ────────────────────────────────────────── */
        hr { margin: 10px 0 !important; border-color: #F3F4F6 !important; }
        small, .stCaption { color: #6B7280 !important; font-size: 0.74rem !important; }

        /* ── Scrollbar ──────────────────────────────────────── */
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 2px; }
        ::-webkit-scrollbar-thumb:hover { background: #2563EB; }

        /* ── Column spacing ─────────────────────────────────── */
        div[data-testid="stColumns"] { gap: 10px !important; }

        /* ── Spinner ────────────────────────────────────────── */
        div[data-testid="stSpinner"] { font-size: 0.82rem !important; }

        /* ── Empty State / Prompt Center ────────────────────── */
        .empty-state-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 44px 24px 32px;
            margin: auto;
        }
        .illustration-box {
            position: relative;
            width: 140px;
            height: 140px;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .blur-bg {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: radial-gradient(ellipse, #DBEAFE 0%, transparent 70%);
            border-radius: 50%;
            opacity: 0.7;
        }
        .main-icon-bubble {
            position: relative;
            z-index: 10;
            background: linear-gradient(135deg, #1E3A5F 0%, #2563EB 100%);
            padding: 16px;
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(37,99,235,0.2);
            transform: rotate(-4deg);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .sub-icon-bubble {
            position: absolute;
            z-index: 11;
            background-color: #FFFFFF;
            border: 1px solid #E5E7EB;
            padding: 10px 12px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            transform: translate(32px, -18px);
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .sub-line-1 {
            height: 5px;
            width: 36px;
            background-color: #BFDBFE;
            border-radius: 999px;
        }
        .sub-line-2 {
            height: 5px;
            width: 22px;
            background-color: #DBEAFE;
            border-radius: 999px;
        }
        .empty-title {
            font-family: 'Outfit', sans-serif !important;
            font-size: 1.4rem !important;
            font-weight: 700 !important;
            color: #111827 !important;
            margin-bottom: 8px !important;
            letter-spacing: -0.3px !important;
        }
        .empty-subtitle {
            font-size: 0.83rem !important;
            color: #6B7280 !important;
            max-width: 320px;
            margin-bottom: 36px !important;
            line-height: 1.5 !important;
        }
        .features-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            width: 100%;
        }
        .feature-card {
            background-color: #FFFFFF;
            padding: 14px;
            border-radius: 12px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            border: 1px solid #E5E7EB;
            display: flex;
            align-items: center;
            gap: 12px;
            text-align: left;
            transition: box-shadow 0.2s ease;
        }
        .feature-card:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .feature-icon-wrapper {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        .feature-icon-green  { background-color: #ECFDF5; color: #059669; }
        .feature-icon-purple { background-color: #F5F3FF; color: #7C3AED; }
        .feature-icon-blue   { background-color: #EFF6FF; color: #2563EB; }
        .feature-text-group {
            display: flex;
            flex-direction: column;
        }
        .feature-card-title {
            font-family: 'Inter', sans-serif !important;
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            color: #111827 !important;
            margin: 0 0 2px 0 !important;
        }
        .feature-card-desc {
            font-size: 0.62rem !important;
            color: #6B7280 !important;
            line-height: 1.35 !important;
            margin: 0 !important;
        }

        /* ── Glass workspace overrides ─────────────────────── */
        html, body, [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 10% 8%, rgba(56, 189, 248, 0.28), transparent 30rem),
                radial-gradient(circle at 92% 14%, rgba(129, 140, 248, 0.24), transparent 26rem),
                radial-gradient(circle at 56% 100%, rgba(20, 184, 166, 0.16), transparent 31rem),
                linear-gradient(135deg, #061321 0%, #0a2133 48%, #102838 100%) !important;
            background-attachment: fixed !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            background: transparent !important;
        }
        div[data-element-id="top_header_container"] {
            background: rgba(255, 255, 255, 0.70) !important;
            border: 1px solid rgba(255, 255, 255, 0.66) !important;
            border-width: 0 0 1px 0 !important;
            box-shadow: 0 12px 35px rgba(2, 12, 27, 0.18) !important;
            backdrop-filter: blur(22px) saturate(145%) !important;
            -webkit-backdrop-filter: blur(22px) saturate(145%) !important;
        }
        div[data-element-id="left_sidebar_container"],
        div[data-testid="stColumn"]:has([data-testid="stChatMessage"]) > div[data-testid="stVerticalBlock"],
        .panel-card,
        .feature-card {
            background: rgba(255, 255, 255, 0.64) !important;
            border: 1px solid rgba(255, 255, 255, 0.66) !important;
            box-shadow: 0 16px 38px rgba(2, 12, 27, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.66) !important;
            backdrop-filter: blur(18px) saturate(135%) !important;
            -webkit-backdrop-filter: blur(18px) saturate(135%) !important;
        }
        div[data-element-id="left_sidebar_container"] {
            background: rgba(255, 255, 255, 0.48) !important;
        }
        div[data-testid="stColumn"]:has([data-testid="stChatMessage"]) [data-testid="stBottom"] {
            background: rgba(255, 255, 255, 0.30) !important;
            border-top-color: rgba(148, 163, 184, 0.28) !important;
            backdrop-filter: blur(16px) !important;
        }

        /* Black glass input surface — #070B14 at 70% opacity. */
        div[data-testid="stChatInput"],
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea {
            background: rgba(7, 11, 20, 0.70) !important;
            color: #F8FAFC !important;
            border: 1px solid rgba(148, 163, 184, 0.38) !important;
            border-radius: 10px !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 10px 24px rgba(2, 12, 27, 0.15) !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
        }
        div[data-testid="stChatInput"] textarea,
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea {
            color: #F8FAFC !important;
            caret-color: #7DD3FC !important;
        }
        div[data-testid="stChatInput"] textarea::placeholder,
        div[data-testid="stTextInput"] input::placeholder,
        div[data-testid="stTextArea"] textarea::placeholder {
            color: #94A3B8 !important;
        }
        div[data-testid="stChatInput"]:focus-within,
        div[data-testid="stTextInput"]:focus-within input,
        div[data-testid="stTextArea"]:focus-within textarea {
            border-color: rgba(56, 189, 248, 0.86) !important;
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.17), inset 0 1px 0 rgba(255, 255, 255, 0.10), 0 12px 28px rgba(2, 12, 27, 0.25) !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # ── Command bar (full-width container, single row) ───────────────────────
    with st.container(key="top_header_container"):
        c1, c2, c3, c4 = st.columns([5.3, 1.4, 0.9, 0.9])
        with c1:
            st.markdown("""
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="padding: 8px; background-color: #0F172A; border-radius: 8px; color: #EAB308; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                        <svg width="18" height="18" fill="currentColor" viewBox="0 0 20 20"><path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1a1 1 0 112 0v1a1 1 0 11-2 0zM13.536 14.95a1 1 0 010-1.414l.707-.707a1 1 0 111.414 1.414l-.707.707a1 1 0 01-1.414 0zM6.464 14.95a1 1 0 01-1.414 0l-.707-.707a1 1 0 011.414-1.414l.707.707a1 1 0 010 1.414z"></path></svg>
                    </div>
                    <div style="display: flex; flex-direction: column;">
                        <div class="cmd-title">Cyber Incident Response Assistant</div>
                        <div class="cmd-subtitle">AI-Powered Cybercrime Incident Response &nbsp;·&nbsp; India &nbsp;·&nbsp; 1930 Helpline Active</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown("""
                <div style="display: flex; justify-content: flex-end; align-items: center;">
                    <div class="cmd-badge">
                        <span class="live-dot"></span>
                        <span>AI Active</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with c3:
            if st.button("＋ New", key="top_new", use_container_width=True, type="primary"):
                reset_session()
        with c4:
            if st.button("↺ Reset", key="top_reset", use_container_width=True, type="secondary"):
                reset_session()

    # ── Session state shortcuts ───────────────────────────────────────────────
    classification = st.session_state.classification
    category_id = classification.get("category_id") if classification else None
    subcategory_id = classification.get("subcategory_id") if classification else None
    stage = st.session_state.stage

    # ── 3-Column layout: LEFT 18% | CENTER 62% | RIGHT 20% ───────────────────
    left_col, center_col, right_col = st.columns([0.9, 3.1, 1.0], gap="small")

    # ── Complaint package data (computed once, reused in left col) ─────────
    cls_ok  = classification is not None
    sum_ok  = bool((st.session_state.summary or "").strip())
    tl_ok   = bool(st.session_state.timeline)
    ev_ok   = any((st.session_state.evidence or {}).values())

    _cpkg = {
        "description":     st.session_state.incident_description,
        "classification":  st.session_state.classification,
        "summary":         st.session_state.summary,
        "timeline":        st.session_state.timeline,
        "evidence":        st.session_state.evidence,
        "followup_answers": st.session_state.followup_answers,
        "evidence_labels": get_evidence_labels_map(category_id),
        "questions_labels": get_questions_labels_map(),
    }

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — Emergency Actions + Complaint Package
    # ══════════════════════════════════════════════════════════════════════════
    with left_col:
        with st.container(key="left_sidebar_container"):
            render_emergency_actions(category_id)
            render_complaint_package_exports(_cpkg)

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT COLUMN — Playbook, Resources, Intel
    # ══════════════════════════════════════════════════════════════════════════
    with right_col:
        render_response_guide(subcategory_id)
        render_threat_intelligence()

    # ══════════════════════════════════════════════════════════════════════════
    # CENTER COLUMN — AI Conversation (dominant) + progressive case data
    # ══════════════════════════════════════════════════════════════════════════
    with center_col:

        # ── A. Chat history ───────────────────────────────────────────────────
        for idx, msg in enumerate(st.session_state.messages):
            role = msg["role"]
            m_type = msg.get("type", "text")
            avatar = "https://lh3.googleusercontent.com/aida-public/AB6AXuDuR_9O-4alQpABoTNX4wZiQFoDLH3muFRtLkRhmqATKgaWKJG1voaIjy1yU_2DYwC9bIiLmYzQPnaG5D4YFGSVsquBxPJgP3bY95yzwWKZrT0PQv5aPTzxA8QDrE0aW6EdL3MPKyvtvnhDbRqbswI-LG88XHPjt6U4KL0hYfub8OAjAv0-FVR358rcVvJ_A_qnI3y_DYCpzKWDlCyxRl-0yrMpG3Iuw4ek1Gwn-OW--yyjrIBqv5w6bq8mwyPPYJEJihivacPq80V1" if role == "assistant" else "👤"

            with st.chat_message(role, avatar=avatar):
                st.markdown(msg["content"])

                # Inline evidence checklist (in-chat checkboxes)
                if m_type == "evidence_checklist":
                    st.caption("Tick each item as you secure it:")
                    items = get_evidence_items(category_id)
                    for item in items:
                        i_id = item["id"]
                        checked_state = st.session_state.evidence.get(i_id, False)
                        cb_val = st.checkbox(
                            item["label"],
                            value=checked_state,
                            key=f"chat_cb_{idx}_{i_id}"
                        )
                        if cb_val != checked_state:
                            st.session_state.evidence[i_id] = cb_val
                            st.rerun()

                # Quick-reply option chips (only for the last assistant message)
                if m_type == "quick_reply" and idx == len(st.session_state.messages) - 1:
                    options = msg.get("options", [])
                    if options:
                        cols = st.columns(min(len(options), 3))
                        for o_idx, opt in enumerate(options):
                            col_target = cols[o_idx % len(cols)]
                            if col_target.button(opt, key=f"qr_{idx}_{o_idx}", use_container_width=True):
                                st.session_state.messages.append({"role": "user", "content": opt, "type": "text"})

                                if stage == "stage_2_confirming":
                                    if opt == "Manual Override / Choose Other...":
                                        st.session_state.messages.append({
                                            "role": "assistant",
                                            "content": "No problem. Describe the incident in more detail and I will re-classify, or wait for the **Case File** panel to appear so you can select manually.",
                                            "type": "text"
                                        })
                                    else:
                                        subcategories = get_all_subcategories()
                                        matched = next((s for s in subcategories if s["name"] == opt), None)
                                        if matched:
                                            handle_category_select(matched["id"])
                                            st.session_state.messages.append({
                                                "role": "assistant",
                                                "content": f"Confirmed. Mapped to **{matched['name']}**. Incident Playbook and diagnostics loaded.",
                                                "type": "text"
                                            })
                                            st.session_state.stage = "stage_3_followup"
                                            if st.session_state.remaining_questions:
                                                next_q = st.session_state.remaining_questions[0]
                                                if next_q["type"] == "select":
                                                    st.session_state.messages.append({
                                                        "role": "assistant",
                                                        "content": next_q["text"],
                                                        "type": "quick_reply",
                                                        "options": next_q["options"]
                                                    })
                                                else:
                                                    st.session_state.messages.append({
                                                        "role": "assistant",
                                                        "content": next_q["text"],
                                                        "type": "text"
                                                    })
                                            else:
                                                st.session_state.stage = "stage_4_evidence"
                                                st.session_state.messages.append({
                                                    "role": "assistant",
                                                    "content": "No further questions needed. Here is your evidence checklist — please tick what you have preserved:",
                                                    "type": "evidence_checklist"
                                                })

                                elif stage == "stage_3_followup":
                                    if st.session_state.remaining_questions:
                                        active_q = st.session_state.remaining_questions.pop(0)
                                        st.session_state.followup_answers[active_q["id"]] = opt
                                        st.session_state.remaining_questions = get_followup_questions(
                                            subcategory_id, st.session_state.followup_answers
                                        )
                                        if st.session_state.remaining_questions:
                                            next_q = st.session_state.remaining_questions[0]
                                            if next_q["type"] == "select":
                                                st.session_state.messages.append({
                                                    "role": "assistant",
                                                    "content": next_q["text"],
                                                    "type": "quick_reply",
                                                    "options": next_q["options"]
                                                })
                                            else:
                                                st.session_state.messages.append({
                                                    "role": "assistant",
                                                    "content": next_q["text"],
                                                    "type": "text"
                                                })
                                        else:
                                            st.session_state.stage = "stage_4_evidence"
                                            trigger_ai_summary_timeline()
                                            st.session_state.messages.append({
                                                "role": "assistant",
                                                "content": "All diagnostics completed. I've compiled your case file. Please tick items as you secure evidence:",
                                                "type": "evidence_checklist"
                                            })
                                st.rerun()

        if len(st.session_state.messages) <= 1:
            st.markdown(
                '<div class="empty-state-container">'
                '<div class="illustration-box">'
                '<div class="blur-bg"></div>'
                '<div class="main-icon-bubble">'
                '<svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="color:#FFFFFF;">'
                '<path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" stroke-linecap="round" stroke-linejoin="round"></path>'
                '</svg>'
                '</div>'
                '<div class="sub-icon-bubble">'
                '<div class="sub-line-1"></div>'
                '<div class="sub-line-2"></div>'
                '</div>'
                '</div>'
                '<div class="empty-title">Describe the incident</div>'
                '<div class="empty-subtitle">Share as many details as you can. The more information you provide, the better I can assist you.</div>'
                '<div class="features-grid">'
                '<div class="feature-card">'
                '<div class="feature-icon-wrapper feature-icon-green">'
                '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">'
                '<path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" stroke-linecap="round" stroke-linejoin="round"></path>'
                '</svg>'
                '</div>'
                '<div class="feature-text-group">'
                '<div class="feature-card-title">Secure &amp; Confidential</div>'
                '<p class="feature-card-desc">Your data is encrypted and handled securely.</p>'
                '</div>'
                '</div>'
                '<div class="feature-card">'
                '<div class="feature-icon-wrapper feature-icon-purple">'
                '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">'
                '<path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round"></path>'
                '</svg>'
                '</div>'
                '<div class="feature-text-group">'
                '<div class="feature-card-title">AI-Powered Assistance</div>'
                '<p class="feature-card-desc">Trained on cybercrime response best practices.</p>'
                '</div>'
                '</div>'
                '<div class="feature-card">'
                '<div class="feature-icon-wrapper feature-icon-blue">'
                '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">'
                '<path d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" stroke-linecap="round" stroke-linejoin="round"></path>'
                '</svg>'
                '</div>'
                '<div class="feature-text-group">'
                '<div class="feature-card-title">Government Initiative</div>'
                '<p class="feature-card-desc">Backed by national cyber security authorities.</p>'
                '</div>'
                '</div>'
                '</div>'
                '</div>',
                unsafe_allow_html=True
            )

        # ── B. Chat input ─────────────────────────────────────────────────────
        user_input = st.chat_input("Tell me what happened — I'm here to help...")

        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input, "type": "text"})
            # refresh stage after possible rerun
            stage = st.session_state.stage

            if stage == "stage_1_intake":
                st.session_state.incident_description = user_input
                st.session_state.stage = "stage_2_classification"

                with st.spinner("Analyzing your incident..."):
                    result = understand_incident(user_input, get_subcategory_names())

                if "error" in result:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"I couldn't reach the classification engine right now. Could you describe the type of incident in one or two words? Alternatively, your Case File panel will appear shortly so you can select manually.",
                        "type": "text"
                    })
                    st.session_state.stage = "stage_2_confirming"
                else:
                    st.session_state.ai_understanding = result
                    mapped = map_to_official_category(result)
                    st.session_state.classification = mapped
                    subcat_name = mapped.get("subcategory_name")
                    cat_name = mapped.get("category_name")
                    confidence_low = mapped.get("needs_confirmation")

                    if not confidence_low:
                        handle_category_select(mapped.get("subcategory_id"))
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"Understood. This looks like **{subcat_name}** under *{cat_name}*. I've loaded the incident playbook on the right. Let me ask a few quick questions to build your case file.",
                            "type": "text"
                        })
                        st.session_state.stage = "stage_3_followup"

                        if st.session_state.remaining_questions:
                            next_q = st.session_state.remaining_questions[0]
                            if next_q["type"] == "select":
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": next_q["text"],
                                    "type": "quick_reply",
                                    "options": next_q["options"]
                                })
                            else:
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": next_q["text"],
                                    "type": "text"
                                })
                        else:
                            st.session_state.stage = "stage_4_evidence"
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": "No further questions needed. Here is your evidence checklist — please tick what you have preserved:",
                                "type": "evidence_checklist"
                            })
                    else:
                        st.session_state.stage = "stage_2_confirming"
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"I think this fits **{subcat_name}** under *{cat_name}*, but I want to confirm. Which of these best describes your situation?",
                            "type": "quick_reply",
                            "options": [subcat_name, "UPI Related Frauds", "Online Job Fraud", "Manual Override / Choose Other..."]
                        })

            elif stage == "stage_3_followup":
                if st.session_state.remaining_questions:
                    active_q = st.session_state.remaining_questions.pop(0)
                    st.session_state.followup_answers[active_q["id"]] = user_input

                    st.session_state.remaining_questions = get_followup_questions(
                        subcategory_id, st.session_state.followup_answers
                    )

                    if st.session_state.remaining_questions:
                        next_q = st.session_state.remaining_questions[0]
                        if next_q["type"] == "select":
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": next_q["text"],
                                "type": "quick_reply",
                                "options": next_q["options"]
                            })
                        else:
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": next_q["text"],
                                "type": "text"
                            })
                    else:
                        st.session_state.stage = "stage_4_evidence"
                        trigger_ai_summary_timeline()
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "All follow-up questions completed. I've compiled your Case File below. Please tick items as you secure evidence:",
                            "type": "evidence_checklist"
                        })

            elif stage == "stage_4_evidence":
                playbook_context = ""
                if st.session_state.playbook:
                    playbook_context = json.dumps(st.session_state.playbook)

                prompt = f"""You are CFRO (Cyber First Response Officer), a professional cybercrime case officer.
The user is a victim. Incident classification: {subcategory_id}.
Case summary: {st.session_state.summary}
Follow-up details: {json.dumps(st.session_state.followup_answers)}
Playbook: {playbook_context}
User asks: "{user_input}"
Respond in 3-4 sentences: reassuring, practical, action-oriented. Mention helpline 1930 for financial crimes."""

                with st.spinner("Formulating response..."):
                    try:
                        reply = call_azure_openai(
                            [{"role": "user", "content": prompt}],
                            temperature=0.35,
                        )
                    except Exception as e:
                        reply = "Please contact your bank immediately, secure your credentials, and file a report at cybercrime.gov.in. You can also call the national helpline **1930** for financial fraud."

                st.session_state.messages.append({"role": "assistant", "content": reply, "type": "text"})

            st.rerun()

        # ── C. Manual override (only if stage_2_confirming and no classification yet) ──
        if stage == "stage_2_confirming" and not classification:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown('<div class="section-header">🔎 Select Incident Type Manually</div>', unsafe_allow_html=True)
                st.caption("The AI could not classify automatically. Please select the closest matching category:")
                all_subs = get_all_subcategories()
                subcat_options = {sub["id"]: f"{sub['name']}" for sub in all_subs}
                subcat_ids = list(subcat_options.keys())
                chosen_sub_id = st.selectbox(
                    "Category",
                    subcat_ids,
                    format_func=lambda x: subcat_options[x],
                    key="initial_manual_selectbox",
                    label_visibility="collapsed"
                )
                if st.button("Initialise Case File →", key="btn_init_manual", use_container_width=True, type="primary"):
                    handle_category_select(chosen_sub_id)
                    st.session_state.stage = "stage_3_followup"
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Case initialised for **{subcat_options[chosen_sub_id]}**. Playbook loaded. Let me ask a few diagnostic questions.",
                        "type": "text"
                    })
                    st.rerun()

        # ── D. PROGRESSIVE CASE FILE (only when classification exists) ────────
        if classification:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                # Header row with classification badge
                conf_val = float(classification.get('match_confidence', 0) or 0)
                conf_color = "#10B981" if conf_val >= 0.7 else "#F0AD4E"
                st.markdown(f"""
                    <div style='display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;'>
                        <div class="section-header" style='margin-bottom:0; border-bottom:none; padding-bottom:0;'>📁 Active Case File</div>
                        <div style='background:{conf_color}18; color:{conf_color}; border:1px solid {conf_color}40;
                             padding:2px 10px; border-radius:20px; font-size:0.72rem; font-weight:700;'>
                            {classification.get('subcategory_name', 'Unknown')} &nbsp;·&nbsp; {int(conf_val*100)}% match
                        </div>
                    </div>
                    <div style='font-size:0.78rem; color:#7B8FA1; margin-bottom:8px; border-bottom:1px solid #EEF1F6; padding-bottom:8px;'>
                        Category: <strong style='color:#0B3C5D;'>{classification.get('category_name', '')}</strong>
                    </div>
                """, unsafe_allow_html=True)

                # Change category expander
                all_subs = get_all_subcategories()
                subcat_options_cf = {sub["id"]: f"{sub['name']}" for sub in all_subs}
                subcat_ids_cf = list(subcat_options_cf.keys())
                with st.expander("✏️ Change Category"):
                    current_idx = subcat_ids_cf.index(subcategory_id) if subcategory_id in subcat_ids_cf else 0
                    chosen_sub_id_cf = st.selectbox(
                        "cat",
                        subcat_ids_cf,
                        index=current_idx,
                        format_func=lambda x: subcat_options_cf[x],
                        key="manual_override_selectbox",
                        label_visibility="collapsed"
                    )
                    if st.button("Apply", key="btn_apply_override", use_container_width=True):
                        handle_category_select(chosen_sub_id_cf)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"Category updated to **{subcat_options_cf[chosen_sub_id_cf]}**. Playbook refreshed.",
                            "type": "text"
                        })
                        st.rerun()

                # AI Summary (only if generated)
                if st.session_state.summary:
                    st.divider()
                    st.markdown("<div style='font-size:0.75rem; font-weight:600; color:#0B3C5D; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;'>📝 Case Summary</div>", unsafe_allow_html=True)
                    st.session_state.summary = st.text_area(
                        "Summary",
                        value=st.session_state.summary,
                        height=85,
                        key="editable_case_summary",
                        label_visibility="collapsed",
                        help="AI-generated summary — you can edit this directly"
                    )

                # Timeline (only if non-empty)
                if st.session_state.timeline:
                    st.divider()
                    st.markdown("<div style='font-size:0.75rem; font-weight:600; color:#0B3C5D; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;'>🕐 Timeline</div>", unsafe_allow_html=True)
                    timeline = st.session_state.timeline
                    updated_timeline = []
                    for i, entry in enumerate(timeline):
                        tl_c1, tl_c2, tl_c3 = st.columns([1.1, 3.2, 0.4])
                        with tl_c1:
                            t_val = st.text_input(f"t{i}", value=entry.get("time", ""), key=f"tl_t_{i}", label_visibility="collapsed", placeholder="Time")
                        with tl_c2:
                            e_val = st.text_input(f"e{i}", value=entry.get("event", ""), key=f"tl_e_{i}", label_visibility="collapsed", placeholder="Event description")
                        with tl_c3:
                            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
                            if st.button("✕", key=f"del_tl_{i}", help="Remove"):
                                timeline.pop(i)
                                st.session_state.timeline = timeline
                                st.rerun()
                        updated_timeline.append({"time": t_val, "event": e_val})
                    st.session_state.timeline = updated_timeline
                    if st.button("➕ Add Event", key="add_tl_event"):
                        st.session_state.timeline.append({"time": "", "event": ""})
                        st.rerun()

                # Evidence inventory (only during/after stage_4)
                if stage == "stage_4_evidence" or st.session_state.summary_generated:
                    evidence_items = get_evidence_items(category_id)
                    evidence_checked = st.session_state.evidence or {}
                    validated = [it["label"] for it in evidence_items if evidence_checked.get(it["id"], False)]
                    missing = [it["label"] for it in evidence_items if not evidence_checked.get(it["id"], False)]

                    if evidence_items:
                        st.divider()
                        ev_c1, ev_c2 = st.columns(2)
                        with ev_c1:
                            st.markdown(f"<div style='font-size:0.73rem; font-weight:700; color:#10B981; margin-bottom:3px;'>✓ COLLECTED ({len(validated)})</div>", unsafe_allow_html=True)
                            if validated:
                                for v in validated:
                                    st.markdown(f"<div style='font-size:0.76rem; color:#1C2B3A; padding-left:8px; margin-bottom:1px;'>✓ {v}</div>", unsafe_allow_html=True)
                            else:
                                st.caption("None yet")
                        with ev_c2:
                            st.markdown(f"<div style='font-size:0.73rem; font-weight:700; color:#D9534F; margin-bottom:3px;'>⚠ PENDING ({len(missing)})</div>", unsafe_allow_html=True)
                            for m in missing[:5]:
                                st.markdown(f"<div style='font-size:0.76rem; color:#D9534F; padding-left:8px; margin-bottom:1px;'>⚠ {m}</div>", unsafe_allow_html=True)
                            if len(missing) > 5:
                                st.caption(f"+ {len(missing)-5} more")

                # Regenerate button (only if summary was generated)
                if st.session_state.summary_generated:
                    st.divider()
                    if st.button("🔄 Regenerate Case File", key="regen_cf", use_container_width=True, type="secondary"):
                        with st.spinner("Regenerating..."):
                            trigger_ai_summary_timeline()
                        st.rerun()


@st.dialog("Playbook Library", width="large")
def render_playbook_library():
    """Display every local Markdown playbook in a closeable catalogue."""
    playbook_root = Path(__file__).parent / "playbooks"
    playbooks = sorted(playbook_root.rglob("*.md"), key=lambda path: str(path).lower())

    close_col, count_col = st.columns([1, 4])
    with close_col:
        if st.button("Close", key="close_playbooks", use_container_width=True):
            st.session_state.show_playbooks = False
            st.rerun()
    with count_col:
        st.markdown(
            f'<p class="playbook-count">{len(playbooks)} response playbooks</p>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<p class="playbook-intro">Browse the complete operational guidance library. '
        'Open any item to read its formatted Markdown content.</p>',
        unsafe_allow_html=True,
    )

    current_group = None
    for playbook_path in playbooks:
        relative_path = playbook_path.relative_to(playbook_root)
        group = (
            "General"
            if relative_path.parent == Path(".")
            else relative_path.parent.name.replace("_", " ").replace("-", " ").title()
        )
        if group != current_group:
            st.markdown(f'<h2 class="playbook-group">{group}</h2>', unsafe_allow_html=True)
            current_group = group

        title = playbook_path.stem.replace("-", " ").replace("_", " ").title()
        with st.expander(title, expanded=False):
            st.markdown(playbook_path.read_text(encoding="utf-8"))


def initialise_investigation_agent() -> None:
    """Create the persistent agent.py conversation state for this browser session."""
    if "agent_messages" in st.session_state:
        return

    evaluation_matrix = load_evaluation_matrix()
    st.session_state.agent_messages = [
        {"role": "system", "content": load_agent_prompt(evaluation_matrix)}
    ]
    st.session_state.verifier_prompt = load_verifier_prompt(evaluation_matrix)


def build_agent_pdf_case_data(final_summary: str) -> dict:
    """Adapt the agent conversation to the existing CIRA PDF report schema."""
    messages = st.session_state.get("chat_messages", [])
    user_messages = [
        message["content"]
        for message in messages
        if message.get("role") == "user"
    ]
    classification = st.session_state.get("active_classification")
    category_id = classification.get("category_id") if classification else None

    timeline = [
        {"time": f"User message {index}", "event": message[:180]}
        for index, message in enumerate(user_messages, start=1)
    ]
    return {
        "description": user_messages[0] if user_messages else "",
        "classification": classification,
        "summary": final_summary,
        "timeline": timeline,
        "evidence": {},
        "followup_answers": {},
        "evidence_labels": get_evidence_labels_map(category_id),
        "questions_labels": {},
    }


def generate_final_report_pdf(final_summary: str) -> bytes | None:
    """Create a downloadable PDF without preventing the final response from rendering."""
    try:
        return bytes(generate_pdf_report(build_agent_pdf_case_data(final_summary)))
    except Exception:
        return None


def is_final_case_summary(reply: str) -> bool:
    """Recognise the report structure required by agent.md even if verification lags."""
    normalized = reply.lower()
    required_sections = ("case summary", "timeline", "immediate next steps")
    return all(section in normalized for section in required_sections)


def run_investigation_turn(
    message: str,
    *,
    user_message_already_rendered: bool = False,
    replace_waiting_message: bool = False,
) -> None:
    """Run one full Investigation Officer and Evidence Verifier turn from agent.py."""
    if not user_message_already_rendered:
        st.session_state.chat_messages.append({"role": "user", "content": message})
    initialise_investigation_agent()

    # Classification is separate by design: agent.py investigates the case,
    # while the official taxonomy determines which Markdown guide to display.
    if not st.session_state.active_classification:
        result = understand_incident(message, get_subcategory_names())
        if "error" not in result:
            classification = map_to_official_category(result)
            st.session_state.active_classification = classification
            st.session_state.active_playbook = load_playbook(classification["subcategory_id"])

    agent_messages = st.session_state.agent_messages
    agent_messages.append({"role": "user", "content": message})

    try:
        agent_output, raw_reply = call_agent(agent_messages)
        verifier_output, _ = call_verifier(
            st.session_state.verifier_prompt,
            agent_messages,
            agent_output,
        )

        if verifier_output["status"] == "verified":
            if agent_output["status"] != "complete":
                agent_output, raw_reply = call_agent(
                    agent_messages,
                    {
                        **verifier_output,
                        "feedback_to_investigator": (
                            "The evidence is verified as report-ready. Produce the final case "
                            "summary, timeline, available evidence, unknown details, and "
                            "immediate next steps in a calm, supportive tone."
                        ),
                    },
                )
                agent_output["status"] = "complete"
        else:
            agent_output, raw_reply = call_agent(agent_messages, verifier_output)
            agent_output["status"] = "investigating"

        agent_messages.append({"role": "assistant", "content": raw_reply})
        reply = agent_output["reply"]
        st.session_state.agent_status = agent_output["status"]
    except Exception:
        st.session_state.agent_status = "investigating"
        reply = (
            "I’m unable to reach the Investigation Officer right now. Please try again "
            "shortly; if money was lost, call 1930 and contact your bank immediately."
        )

    if replace_waiting_message and st.session_state.chat_messages[-1].get("pending"):
        st.session_state.chat_messages[-1] = {"role": "assistant", "content": reply}
    else:
        st.session_state.chat_messages.append({"role": "assistant", "content": reply})
    if st.session_state.get("agent_status") == "complete" or is_final_case_summary(reply):
        st.session_state.agent_status = "complete"
        st.session_state.final_report_pdf = generate_final_report_pdf(reply)


def render_active_playbook() -> None:
    """Render the playbook associated with the most recent agent classification."""
    classification = st.session_state.get("active_classification")
    playbook = st.session_state.get("active_playbook")
    if not classification or not playbook:
        return

    with st.container(key="active_playbook_container"):
        st.markdown('<p class="active-playbook-kicker">Active playbook</p>', unsafe_allow_html=True)
        st.markdown(
            f'<h2 class="active-playbook-title">{classification["subcategory_name"]}</h2>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p class="active-playbook-copy">{classification["category_name"]} · '
            f'{round(classification["match_confidence"] * 100)}% confidence</p>',
            unsafe_allow_html=True,
        )
        if playbook.get("available"):
            for section, content in playbook.get("sections", {}).items():
                with st.expander(section, expanded=section == next(iter(playbook["sections"]), None)):
                    st.markdown(content)
        else:
            st.info(playbook.get("message", "This playbook is not available yet."))


@st.dialog("Response playbook", width="large")
def show_active_playbook_dialog() -> None:
    """Display the currently classified Markdown playbook in a modal."""
    render_active_playbook()


def main():
    """Render the focused, single-prompt interface."""
    st.set_page_config(
        page_title="CIRA",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
            min-height: 100%;
            background: #FFFFFF !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }
        [data-testid="stMain"] {
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }
        header[data-testid="stHeader"], footer, [data-testid="stSidebar"] { display: none !important; }
        .block-container {
            min-height: 100vh;
            max-width: 1240px !important;
            padding: 7rem 1.25rem 9rem !important;
        }
        .block-container > div { width: 100%; }
        /* Centered, readable conversation column */
        div.st-key-conversation_workspace {
            width: min(100%, 760px);
            margin: 0 auto;
            padding: 0 1rem 2rem;
            box-sizing: border-box;
        }
        @media (min-width: 1181px) {
            div.st-key-conversation_workspace {
                margin-right: 0;
                margin-left: calc(30% - 260px);
            }
        }
        /* "Response playbook" launcher button */
        div.st-key-conversation_workspace .stButton > button {
            width: auto;
            margin: 0 0 1.25rem;
            border: 1px solid #E5E7EB !important;
            border-radius: 999px !important;
            background: #FFFFFF !important;
            color: #343541 !important;
            font: 600 0.85rem/1 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            padding: 0.5rem 1rem !important;
            box-shadow: none !important;
            transition: border-color 150ms ease, background 150ms ease, transform 150ms ease;
        }
        div.st-key-conversation_workspace .stButton > button:hover {
            border-color: #10A37F !important;
            background: #F7FCFA !important;
            transform: translateY(-1px);
        }
        /* Animated "assistant is typing" indicator for the pending bubble */
        .cira-typing { display: inline-flex; align-items: center; gap: 5px; padding: 2px 0; }
        .cira-typing span {
            width: 7px; height: 7px; border-radius: 50%;
            background: #9CA3AF; display: inline-block;
            animation: cira-typing-bounce 1.2s ease-in-out infinite;
        }
        .cira-typing span:nth-child(2) { animation-delay: 0.18s; }
        .cira-typing span:nth-child(3) { animation-delay: 0.36s; }
        @keyframes cira-typing-bounce {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
            30% { transform: translateY(-5px); opacity: 1; }
        }
        @media (prefers-reduced-motion: reduce) {
            .cira-typing span { animation: none; opacity: 0.7; }
        }
        @media (max-width: 760px) {
            .block-container { padding-right: 0.75rem !important; padding-left: 0.75rem !important; }
            div.st-key-conversation_workspace { padding-right: 0; padding-left: 0; }
        }
        .cira-heading {
            margin: 0 0 0.75rem !important;
            color: #202123 !important;
            font: 600 clamp(2.5rem, 7vw, 4.5rem)/1 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            letter-spacing: -0.075em !important;
            text-align: center;
            animation: cira-enter 700ms cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        /* Compact header once a conversation is underway */
        .cira-heading.is-compact {
            font-size: clamp(1.6rem, 3.5vw, 2.1rem) !important;
            margin: 0 0 1.5rem !important;
        }
        .cira-tagline {
            margin: 0 auto 2.5rem !important;
            max-width: 560px;
            text-align: center;
            color: #6B6C7B !important;
            font: 400 clamp(0.95rem, 2vw, 1.1rem)/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            letter-spacing: -0.01em;
            animation: cira-enter 700ms cubic-bezier(0.16, 1, 0.3, 1) 120ms both;
        }
        @keyframes cira-enter {
            from { opacity: 0; transform: translateY(18px); letter-spacing: -0.02em; }
            to { opacity: 1; transform: translateY(0); letter-spacing: -0.075em; }
        }
        @media (prefers-reduced-motion: reduce) {
            .cira-heading, .cira-tagline { animation: none; }
        }
        /* Starter suggestion chips */
        div.st-key-suggestion_chips_container {
            max-width: 720px;
            margin: 0 auto 1rem;
            animation: cira-enter 700ms cubic-bezier(0.16, 1, 0.3, 1) 220ms both;
        }
        div.st-key-suggestion_chips_container button {
            width: 100%;
            min-height: 100%;
            text-align: left !important;
            white-space: normal !important;
            padding: 0.85rem 1rem !important;
            border: 1px solid #E1E3E8 !important;
            border-radius: 14px !important;
            background: #FFFFFF !important;
            color: #343541 !important;
            font: 450 0.9rem/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease !important;
        }
        div.st-key-suggestion_chips_container button:hover {
            border-color: #10A37F !important;
            background: #F7FCFA !important;
            transform: translateY(-2px);
            box-shadow: 0 7px 16px rgba(16, 163, 127, 0.12) !important;
        }
        div.st-key-suggestion_chips_container button p {
            text-align: left !important;
        }
        .call-1930 {
            position: fixed;
            top: 1.25rem;
            left: 1.25rem;
            z-index: 10;
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            padding: 0.7rem 1rem;
            border: 1px solid #B91C1C;
            border-radius: 999px;
            background: linear-gradient(135deg, #EF4444, #B91C1C);
            color: #FFFFFF !important;
            font: 700 0.88rem/1 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            letter-spacing: -0.01em;
            text-decoration: none !important;
            box-shadow: 0 8px 18px rgba(185, 28, 28, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.22);
            transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
        }
        .call-1930:hover {
            background: linear-gradient(135deg, #F05252, #DC2626);
            color: #FFFFFF !important;
            transform: translateY(-2px);
            box-shadow: 0 12px 22px rgba(185, 28, 28, 0.32), inset 0 1px 0 rgba(255, 255, 255, 0.25);
        }
        .call-1930:focus-visible { outline: 3px solid rgba(239, 68, 68, 0.28); outline-offset: 3px; }
        .call-1930 svg { width: 1rem; height: 1rem; fill: currentColor; }
        div[role="dialog"] { border-radius: 20px !important; }
        .playbook-count { margin: 0.5rem 0 0 !important; color: #6B7280; font-size: 0.88rem; }
        .playbook-intro { color: #4B5563; line-height: 1.55; margin: 0.5rem 0 1.5rem !important; }
        .playbook-group {
            color: #202123 !important;
            font: 650 1rem/1.3 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            margin: 1.5rem 0 0.6rem !important;
        }
        /* Free, card-less playbook surface — scrolls within the viewport. */
        div.st-key-active_playbook_container {
            position: sticky;
            top: 5.5rem;
            min-height: 200px;
            max-height: calc(100vh - 9rem);
            overflow-y: auto;
            overflow-x: hidden;
            padding: 0.25rem 0.75rem 1rem 0.25rem;
            border: none;
            background: transparent;
            scroll-behavior: smooth;
            overscroll-behavior: contain;
        }
        div.st-key-active_playbook_container::-webkit-scrollbar {
            width: 6px;
        }
        div.st-key-active_playbook_container::-webkit-scrollbar-track {
            background: transparent;
        }
        div.st-key-active_playbook_container::-webkit-scrollbar-thumb {
            background: #E1E3E8;
            border-radius: 999px;
        }
        div.st-key-active_playbook_container::-webkit-scrollbar-thumb:hover {
            background: #10A37F;
        }
        .active-playbook-kicker {
            margin: 0 0 0.55rem !important;
            color: #10A37F !important;
            font: 700 0.7rem/1 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }
        .active-playbook-title {
            margin: 0 !important;
            color: #202123 !important;
            font: 650 1.2rem/1.25 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            letter-spacing: -0.025em;
        }
        .active-playbook-copy { margin: 0.55rem 0 1.25rem !important; color: #4B5563; font-size: 0.84rem; line-height: 1.45; }
        div.st-key-active_playbook_container [data-testid="stExpander"] {
            border: 1px solid #E5E7EB !important;
            border-radius: 10px !important;
            background: #FFFFFF !important;
        }
        div.st-key-active_playbook_container [data-testid="stExpander"] summary,
        div.st-key-active_playbook_container [data-testid="stExpander"] summary * {
            color: #202123 !important;
        }
        div.st-key-active_playbook_container [data-testid="stExpander"] p,
        div.st-key-active_playbook_container [data-testid="stExpander"] li,
        div.st-key-active_playbook_container [data-testid="stExpander"] td,
        div.st-key-active_playbook_container [data-testid="stExpander"] blockquote {
            color: #202123 !important;
        }
        div.st-key-active_playbook_container [data-testid="stExpander"] h1,
        div.st-key-active_playbook_container [data-testid="stExpander"] h2,
        div.st-key-active_playbook_container [data-testid="stExpander"] h3,
        div.st-key-active_playbook_container [data-testid="stExpander"] h4,
        div.st-key-active_playbook_container [data-testid="stExpander"] strong,
        div.st-key-active_playbook_container [data-testid="stExpander"] th {
            color: #111827 !important;
        }
        div.st-key-active_playbook_container [data-testid="stExpander"] a { color: #0E7490 !important; }
        /* Streamlit may portal expanded content outside the keyed container. */
        [data-testid="stExpander"] p,
        [data-testid="stExpander"] li,
        [data-testid="stExpander"] td,
        [data-testid="stExpander"] blockquote { color: #202123 !important; }
        [data-testid="stExpander"] h1,
        [data-testid="stExpander"] h2,
        [data-testid="stExpander"] h3,
        [data-testid="stExpander"] h4,
        [data-testid="stExpander"] strong,
        [data-testid="stExpander"] th,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary * { color: #111827 !important; }
        [data-testid="stExpander"] a { color: #0E7490 !important; }
        [data-testid="stChatMessageContent"],
        [data-testid="stChatMessageContent"] p,
        [data-testid="stChatMessageContent"] li,
        [data-testid="stChatMessageContent"] blockquote {
            color: #202123 !important;
        }
        [data-testid="stChatMessageContent"] h1,
        [data-testid="stChatMessageContent"] h2,
        [data-testid="stChatMessageContent"] h3,
        [data-testid="stChatMessageContent"] h4,
        [data-testid="stChatMessageContent"] strong {
            color: #111827 !important;
        }
        [data-testid="stChatMessageContent"] a { color: #0E7490 !important; }
        /* ── Chat bubbles ───────────────────────────────────── */
        [data-testid="stChatMessage"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0.35rem 0 !important;
            gap: 0.65rem !important;
        }
        /* Assistant: clean, left-aligned, no box */
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) [data-testid="stChatMessageContent"],
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
            background: transparent !important;
            border: none !important;
            padding: 0.4rem 0 !important;
        }
        /* User: compact, right-aligned bubble */
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]),
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
            flex-direction: row-reverse !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"],
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
            flex: 0 1 auto !important;
            width: auto !important;
            max-width: 76% !important;
            padding: 0.7rem 1rem !important;
            border: none !important;
            border-radius: 18px 18px 4px 18px !important;
            background: #EEF2F7 !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stChatMessageContent"] > div,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] > div {
            background: transparent !important;
        }
        /* Slightly smaller, calmer avatars */
        [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessageAvatarAssistant"],
        [data-testid="chatAvatarIcon-user"],
        [data-testid="chatAvatarIcon-assistant"] {
            width: 2rem !important;
            height: 2rem !important;
            flex-shrink: 0 !important;
        }
        /* ── Bottom docked input — free & elegant (no card) ──── */
        /* Transparent bar with a soft fade so messages dissolve behind it. */
        [data-testid="stBottom"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }
        [data-testid="stBottom"] > div {
            background: #FFFFFF !important;
            padding-bottom: 1rem !important;
        }
        [data-testid="stBottomBlockContainer"] {
            max-width: 760px !important;
            margin: 0 auto !important;
            padding: 1.25rem 1rem 0 !important;
            background: transparent !important;
        }
        /* The rounded input shell */
        [data-testid="stChatInput"] {
            position: relative !important;
            max-width: 760px;
            margin: 0 auto;
            border: 1px solid #E5E7EB !important;
            border-radius: 26px !important;
            background: #FFFFFF !important;
            box-shadow: none !important;
            transition: border-color 160ms ease, box-shadow 160ms ease;
        }
        /* Strip the inner BaseWeb wrappers so only the shell shows, and let
           the text field span the full width (fixes text starting mid-box). */
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] [data-baseweb="textarea"],
        [data-testid="stChatInput"] [data-baseweb="base-input"] {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            width: 100% !important;
            flex: 1 1 auto !important;
        }
        [data-testid="stChatInput"] textarea {
            width: 100% !important;
            min-height: 56px !important;
            max-height: 200px !important;
            /* leave room for the send button on the right */
            padding: 0.95rem 3.5rem 0.95rem 1.4rem !important;
            background: transparent !important;
            color: #1F2937 !important;
            caret-color: #10A37F !important;
            text-align: left !important;
            font: 400 1rem/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            resize: none !important;
        }
        [data-testid="stChatInput"] textarea::placeholder {
            color: #8E8EA0 !important;
            opacity: 1;
            text-align: left !important;
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: #10A37F !important;
            box-shadow: none !important;
        }
        /* ── Send button ─────────────────────────────────────── */
        [data-testid="stChatInputSubmitButton"] {
            position: absolute;
            right: 0.6rem;
            bottom: 0.6rem;
            width: 2.25rem !important;
            height: 2.25rem !important;
            border-radius: 50% !important;
            background: #10A37F !important;
            color: #FFFFFF !important;
            border: none !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            transition: background 160ms ease, transform 160ms ease, opacity 160ms ease;
        }
        [data-testid="stChatInputSubmitButton"]:hover:not(:disabled) {
            background: #0E8E6E !important;
            transform: scale(1.05);
        }
        [data-testid="stChatInputSubmitButton"]:disabled {
            background: #E1E3E8 !important;
            color: #FFFFFF !important;
            opacity: 1 !important;
        }
        [data-testid="stChatInputSubmitButton"] svg {
            width: 1.1rem !important;
            height: 1.1rem !important;
            fill: currentColor !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Floating helpline button (kept) ──────────────────────────────────────
    st.markdown(
        '''<a class="call-1930" href="tel:1930" aria-label="Call cyber fraud helpline 1930">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.62 10.79a15.46 15.46 0 006.59 6.59l2.2-2.2a1 1 0 011.02-.24c1.12.37 2.31.57 3.57.57a1 1 0 011 1V20a1 1 0 01-1 1C10.61 21 3 13.39 3 4a1 1 0 011-1h3.5a1 1 0 011 1c0 1.25.2 2.45.57 3.57a1 1 0 01-.25 1.02l-2.2 2.2z"/></svg>
            <span>Call 1930</span>
        </a>''',
        unsafe_allow_html=True,
    )

    # ── Emergency & Action card — floats on the left, white, borderless ───────
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        .ea-card {
            position: fixed !important;
            top: 5rem !important;
            left: 1.25rem !important;
            width: 15.5rem;
            z-index: 9999 !important;
            inset: 5rem auto auto 1.25rem !important;
            transform: none !important;
            will-change: auto;
            font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #FFFFFF;
            border-radius: 18px;
            padding: 1.15rem 1.1rem;
            box-shadow: none;
        }
        .ea-card__kicker {
            margin: 0 0 0.2rem !important;
            font: 700 0.66rem/1 'Space Grotesk', sans-serif !important;
            letter-spacing: 0.16em; text-transform: uppercase; color: #10A37F !important;
        }
        .ea-card__title {
            margin: 0 0 0.9rem !important;
            font: 600 1.1rem/1.15 'Space Grotesk', sans-serif !important;
            letter-spacing: -0.01em; color: #111827 !important;
        }
        .ea-item {
            display: flex; gap: 0.7rem; align-items: flex-start;
            padding: 0.55rem 0; text-decoration: none !important;
        }
        .ea-badge {
            flex: 0 0 auto; min-width: 3rem; height: 1.9rem; padding: 0 0.5rem;
            display: inline-flex; align-items: center; justify-content: center;
            border-radius: 9px; font: 700 0.7rem/1 'Space Grotesk', sans-serif;
            letter-spacing: 0.04em;
        }
        .ea-badge--red   { background: #FEE2E2; color: #DC2626 !important; }
        .ea-badge--amber { background: #FEF3C7; color: #D97706 !important; }
        .ea-badge--blue  { background: #E0F2FE; color: #0284C7 !important; }
        .ea-badge--green { background: #D1FAE5; color: #059669 !important; }
        .ea-body { display: flex; flex-direction: column; gap: 2px; }
        .ea-title {
            font: 700 0.8rem/1.2 'Space Grotesk', sans-serif !important;
            letter-spacing: 0.03em; color: #1F2937 !important;
        }
        .ea-desc {
            font: 400 0.72rem/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            color: #6B7280 !important;
        }
        a.ea-item { transition: transform 150ms ease; }
        a.ea-item:hover { transform: translateX(2px); }
        a.ea-item:hover .ea-title { color: #10A37F !important; }
        @media (max-width: 1180px) { .ea-card { display: none; } }
        </style>
        <div class="ea-card">
            <p class="ea-card__kicker">Emergency &amp; Action</p>
            <p class="ea-card__title">First response steps</p>
            <a class="ea-item" href="tel:1930" aria-label="Call helpline 1930">
                <span class="ea-badge ea-badge--red">1930</span>
                <span class="ea-body">
                    <span class="ea-title">REPORT FRAUD</span>
                    <span class="ea-desc">Call the national helpline at 1930 immediately to freeze financial losses.</span>
                </span>
            </a>
            <div class="ea-item">
                <span class="ea-badge ea-badge--amber">NET</span>
                <span class="ea-body">
                    <span class="ea-title">GO OFFLINE</span>
                    <span class="ea-desc">Disconnect compromised systems or mobile phones from Wi-Fi / Mobile Data.</span>
                </span>
            </div>
            <div class="ea-item">
                <span class="ea-badge ea-badge--blue">KEEP</span>
                <span class="ea-body">
                    <span class="ea-title">DON'T DELETE</span>
                    <span class="ea-desc">Preserve all communication logs, chats, SMS alert texts, and transaction screens.</span>
                </span>
            </div>
            <div class="ea-item">
                <span class="ea-badge ea-badge--green">SAFE</span>
                <span class="ea-body">
                    <span class="ea-title">NEVER SHARE</span>
                    <span class="ea-desc">Never share passwords, bank OTPs, or click on files received from unknown actors.</span>
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("show_playbooks", False):
        render_playbook_library()

    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("active_classification", None)
    st.session_state.setdefault("active_playbook", None)

    # Remove placeholders and duplicate adjacent user entries left by the
    # earlier rerun-based composer flow.
    cleaned_messages = []
    for message in st.session_state.chat_messages:
        if message.get("pending"):
            continue
        if (
            cleaned_messages
            and message.get("role") == "user"
            and cleaned_messages[-1].get("role") == "user"
            and message.get("content") == cleaned_messages[-1].get("content")
        ):
            continue
        cleaned_messages.append(message)
    st.session_state.chat_messages = cleaned_messages
    st.session_state.pop("pending_agent_message", None)

    # Support a report-ready response that was rendered before PDF export was
    # added, or whose verifier status was still investigating at that time.
    latest_assistant_reply = next(
        (
            message["content"]
            for message in reversed(st.session_state.chat_messages)
            if message.get("role") == "assistant"
        ),
        "",
    )
    if is_final_case_summary(latest_assistant_reply) and not st.session_state.get("final_report_pdf"):
        st.session_state.agent_status = "complete"
        st.session_state.final_report_pdf = generate_final_report_pdf(latest_assistant_reply)

    has_conversation = bool(st.session_state.chat_messages)

    # Composer motion: float the input in the vertical middle on first load so
    # it's the obvious focal point, then glide it down to the bottom the moment
    # the conversation starts (one-time animation, tracked via a session flag).
    docked_before = st.session_state.get("input_docked", False)
    if has_conversation:
        st.session_state["input_docked"] = True

    if not has_conversation:
        st.markdown(
            """
            <style>
            [data-testid="stBottom"] {
                transform: translateY(-36vh);
                animation: cira-input-enter 700ms cubic-bezier(0.16, 1, 0.3, 1) both;
                will-change: transform;
            }
            @keyframes cira-input-enter {
                from { transform: translateY(calc(-36vh + 18px)); opacity: 0; }
                to   { transform: translateY(-36vh); opacity: 1; }
            }
            @media (prefers-reduced-motion: reduce) {
                [data-testid="stBottom"] { animation: none; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    elif not docked_before:
        st.markdown(
            """
            <style>
            [data-testid="stBottom"] {
                animation: cira-input-dock 720ms cubic-bezier(0.16, 1, 0.3, 1) both;
                will-change: transform;
            }
            @keyframes cira-input-dock {
                from { transform: translateY(-36vh); }
                to   { transform: translateY(0); }
            }
            @media (prefers-reduced-motion: reduce) {
                [data-testid="stBottom"] { animation: none; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    # Keep the composer in one predictable place. This rule intentionally comes
    # after the optional entry-animation styles above so it wins on every rerun.
    st.markdown(
        """
        <style>
        [data-testid="stBottom"] {
            position: fixed !important;
            right: 0 !important;
            bottom: 0 !important;
            left: 0 !important;
            z-index: 20 !important;
            transform: none !important;
            animation: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Adaptive header: a welcoming hero before the first message,
    # a compact title once the conversation is underway.
    heading_class = "cira-heading is-compact" if has_conversation else "cira-heading"
    st.markdown(f'<h1 class="{heading_class}">CIRA</h1>', unsafe_allow_html=True)

    if not has_conversation:
        st.markdown(
            '<p class="cira-tagline">Your Cyber Incident Response Assistant. '
            'Describe what happened and I\'ll classify the incident, open the right '
            'response playbook, and guide your first steps.</p>',
            unsafe_allow_html=True,
        )

    has_active_playbook = bool(
        st.session_state.active_classification and st.session_state.active_playbook
    )

    # Widen the workspace when the playbook panel is present; keep the chat
    # comfortably centred when it isn't.
    if has_active_playbook:
        st.markdown(
            "<style>div.st-key-conversation_workspace{width:min(100%,1180px)!important;}</style>",
            unsafe_allow_html=True,
        )

    with st.container(key="conversation_workspace"):
        if has_active_playbook:
            chat_col, playbook_col = st.columns([1.55, 1], gap="large")
        else:
            chat_col, playbook_col = st.container(), None

        with chat_col:
            chat_feed = st.container()
            with chat_feed:
                for chat_message in st.session_state.chat_messages:
                    if chat_message.get("pending"):
                        continue
                    with st.chat_message(chat_message["role"]):
                        st.markdown(chat_message["content"])

            final_report_pdf = st.session_state.get("final_report_pdf")
            if st.session_state.get("agent_status") == "complete" and final_report_pdf:
                st.download_button(
                    "Download final report (PDF)",
                    data=final_report_pdf,
                    file_name="CIRA_case_report.pdf",
                    mime="application/pdf",
                    key="download_final_report_pdf",
                    use_container_width=False,
                )

        if playbook_col is not None:
            with playbook_col:
                render_active_playbook()

    user_message = st.chat_input("Message CIRA…")
    if user_message:
        first_classification = st.session_state.active_classification is None
        st.session_state.chat_messages.append({"role": "user", "content": user_message})
        with chat_feed:
            with st.chat_message("user"):
                st.markdown(user_message)
            with st.chat_message("assistant"):
                response_slot = st.empty()
                response_slot.markdown(
                    '<span class="cira-typing" aria-label="Assistant is responding">'
                    '<span></span><span></span><span></span></span>',
                    unsafe_allow_html=True,
                )
                run_investigation_turn(user_message, user_message_already_rendered=True)
                response_slot.markdown(st.session_state.chat_messages[-1]["content"])
                if st.session_state.get("agent_status") == "complete":
                    final_report_pdf = st.session_state.get("final_report_pdf")
                    if final_report_pdf:
                        st.download_button(
                            "Download final report (PDF)",
                            data=final_report_pdf,
                            file_name="CIRA_case_report.pdf",
                            mime="application/pdf",
                            key="download_final_report_pdf_inline",
                            use_container_width=False,
                        )
        if first_classification:
            # Columns are built at the top of the run, before the model has
            # classified — so on the very first turn the right-hand playbook
            # column doesn't exist yet. Rerun once so the layout reflows with
            # the playbook docked on the right (a single, consistent render).
            st.rerun()


if __name__ == "__main__":
    main()
