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
        }
        header[data-testid="stHeader"], footer, [data-testid="stSidebar"] { display: none !important; }
        .block-container {
            min-height: 100vh;
            max-width: 820px !important;
            padding: clamp(2rem, 24vh, 13rem) 1.25rem !important;
            display: flex;
            align-items: center;
        }
        .block-container > div { width: 100%; }
        [data-testid="stTextArea"] { width: 100%; }
        [data-testid="stTextArea"] label { display: none !important; }
        [data-testid="stTextArea"] textarea {
            min-height: 148px !important;
            padding: 1.1rem 1.25rem !important;
            border: 1px solid #D9D9E3 !important;
            border-radius: 20px !important;
            background: #FFFFFF !important;
            color: #1F2937 !important;
            caret-color: #10A37F !important;
            font: 400 1rem/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            box-shadow: 0 2px 7px rgba(0, 0, 0, 0.08), 0 12px 28px rgba(0, 0, 0, 0.05) !important;
            resize: none !important;
            transition: border-color 160ms ease, box-shadow 160ms ease;
        }
        [data-testid="stTextArea"] textarea::placeholder { color: #8E8EA0 !important; opacity: 1; }
        [data-testid="stTextArea"] textarea:focus {
            border-color: #10A37F !important;
            box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.14), 0 3px 10px rgba(0, 0, 0, 0.10) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.text_area(
        "Prompt",
        key="prompt",
        height=148,
        label_visibility="collapsed",
        placeholder="Message CIRA...",
    )


if __name__ == "__main__":
    main()
