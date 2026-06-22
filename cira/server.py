"""FastAPI Backend Server for CFRO."""

import json
import asyncio
from pathlib import Path
import io
import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

from utils.groq_client import understand_incident, generate_summary_and_timeline, investigate_incident
from utils.classification_mapper import map_to_official_category, get_subcategory_names, get_all_subcategories
from utils.rule_engine import get_followup_questions
from utils.playbook_loader import load_playbook
from utils.pdf_generator import generate_pdf_report
from components.complaint_package_exports import (
    generate_complaint_package_text,
    generate_complaint_package_markdown,
    generate_printable_summary_html
)
from components.evidence_checklist import EVIDENCE_BY_CATEGORY, GENERIC_EVIDENCE

app = FastAPI(title="CFRO API Server")

# Enable CORS for frontend client development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load data helper
DATA_DIR = Path(__file__).resolve().parent / "data"

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    stage: str
    classification: Optional[Dict[str, Any]] = None
    followup_answers: Dict[str, Any] = {}
    remaining_questions: List[Dict[str, Any]] = []
    evidence: Dict[str, bool] = {}
    user_input: str
    summary: Optional[str] = ""
    timeline: Optional[List[Dict[str, Any]]] = []

class SummaryRequest(BaseModel):
    incident_description: str
    classification: Dict[str, Any]
    followup_answers: Dict[str, Any]
    evidence: Dict[str, bool]

@app.get("/api/config")
async def get_config():
    """Load and return workspace configurations and categories."""
    try:
        categories_path = DATA_DIR / "categories.json"
        with open(categories_path, encoding="utf-8") as f:
            categories_data = json.load(f)

        config_path = DATA_DIR / "workspace_config.json"
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)

        return {
            "categories": categories_data.get("categories", []),
            "subcategories": categories_data.get("subcategories", []),
            "national_resources": config_data.get("national_resources", []),
            "threat_intelligence": config_data.get("threat_intelligence", []),
            "evidence_by_category": EVIDENCE_BY_CATEGORY,
            "generic_evidence": GENERIC_EVIDENCE,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/playbook/{subcategory_id}")
async def get_playbook(subcategory_id: str):
    """Load playbook for the given subcategory."""
    return load_playbook(subcategory_id)

@app.post("/api/chat")
async def chat_handler(req: ChatRequest):
    """Handle chat message logic and stage transitions via stateful verifier loop."""
    print("--- CHAT HANDLER: Received request ---")
    try:
        from case_state import CaseState
        from triage import detect_financial_loss_regex, detect_financial_loss_llm, build_triage_notice
        from agent import (
            call_agent,
            call_verifier,
            load_agent_prompt,
            load_verifier_prompt,
            load_evaluation_matrix
        )
        from utils.groq_client import call_groq
        from evidence_registry import CATEGORIES
        import re

        print("--- CHAT HANDLER: Parsing request data ---")
        messages = list(req.messages)
        stage = req.stage
        classification = req.classification
        followup_answers = dict(req.followup_answers)
        evidence = dict(req.evidence)
        user_input = req.user_input
        summary = req.summary or ""
        timeline = list(req.timeline) if req.timeline else []

        # 1. Reconstruct CaseState
        case = CaseState()
        case.financial_loss = followup_answers.get("_triage_financial_loss") == "true"
        case.urgent_notice_shown = followup_answers.get("_triage_urgent_notice_shown") == "true"
        case.phase = followup_answers.get("_triage_phase") or "TRIAGE"
        
        if classification:
            portal_subcat_id = classification.get("subcategory_id")
            PORTAL_TO_EVAL_MAP = {
                "upi-related-frauds": "upi_fraud",
                "internet-banking-related-fraud": "banking_fraud",
                "debit-credit-card-sim-swap-fraud": "sim_swap_fraud",
                "cheating-by-impersonation": "whatsapp_hijack",
                "profile-hacking-identity-theft": "social_media_takeover",
                "e-mail-phishing": "phishing_scam",
                "e-wallet-related-fraud": "qr_code_scam",
                "unauthorised-access-data-breach": "remote_access_scam",
                "damage-to-computer-systems": "mobile_hacking_malware",
                "demat-depository-fraud": "investment_scam",
                "online-job-fraud": "job_scam",
                "any-other-cyber-crime": "ecommerce_fraud",
                "cyber-bullying-stalking-sexting": "sextortion",
            }
            case.matched_category_id = PORTAL_TO_EVAL_MAP.get(portal_subcat_id) or portal_subcat_id
            case.match_confidence = classification.get("match_confidence") or 0.0

        case.summary = summary
        case.timeline = timeline

        for item_id, checked in evidence.items():
            case.evidence_status[item_id] = bool(checked)

        for k, v in followup_answers.items():
            if not k.startswith("_triage_"):
                case.followup_answers[k] = str(v)

        # 1.5 Intercept Early FIR Generation commands
        from agent import wants_fir_generation, wants_to_proceed_anyway, handle_fir_generation_request
        user_wants_fir = wants_fir_generation(user_input)
        user_wants_proceed = wants_to_proceed_anyway(user_input)
        awaiting_partial = followup_answers.get("_triage_awaiting_partial") == "true"
        
        if user_wants_fir or (user_wants_proceed and awaiting_partial):
            confirmed_partial = user_wants_proceed and awaiting_partial
            
            # Estimate last verifier status
            last_verifier_status = "needs_more_information"
            if classification and case.matched_category_id:
                missing = case.missing_required_labels()
                if not missing:
                    last_verifier_status = "verified"
            
            message, pdf_bytes = handle_fir_generation_request(
                case, last_verifier_status, confirmed_partial
            )
            
            is_complete = pdf_bytes is not None
            if is_complete:
                case.phase = "REPORT_READY"
                # If summary is not generated, call agent to generate a final summary and timeline
                if not case.summary:
                    evaluation_matrix = load_evaluation_matrix()
                    agent_prompt = load_agent_prompt(evaluation_matrix)
                    agent_messages = [{"role": "system", "content": agent_prompt}] + [
                        {"role": m["role"], "content": m["content"]} for m in messages
                    ] + [{"role": "user", "content": user_input}]
                    completion_feedback = {
                        "status": "verified",
                        "feedback_to_investigator": (
                            "The user requested to proceed anyway. Produce the final case "
                            "summary and timeline using the available details."
                        )
                    }
                    agent_output, _ = await asyncio.to_thread(call_agent, agent_messages, completion_feedback)
                    if agent_output.get("summary"):
                        case.summary = agent_output["summary"]
                    if isinstance(agent_output.get("timeline"), list):
                        case.timeline = agent_output["timeline"]
            
            # Format assistant response
            reply_text = message
            assistant_msg = {
                "role": "assistant",
                "content": reply_text,
                "type": "evidence_checklist" if is_complete else "text",
                "options": []
            }
            messages.append({"role": "user", "content": user_input, "type": "text"})
            messages.append(assistant_msg)
            
            res_evidence = {k: bool(v) for k, v in case.evidence_status.items()}
            res_followup_answers = {**case.followup_answers}
            res_followup_answers["_triage_financial_loss"] = "true" if case.financial_loss else "false"
            res_followup_answers["_triage_urgent_notice_shown"] = "true" if case.urgent_notice_shown else "false"
            res_followup_answers["_triage_phase"] = case.phase
            res_followup_answers["_triage_awaiting_partial"] = "true" if (user_wants_fir and pdf_bytes is None) else "false"
            
            res_classification = classification
            if case.matched_category_id:
                from utils.classification_mapper import get_all_subcategories
                EVAL_TO_PORTAL_MAP = {
                    "upi_fraud": "upi-related-frauds",
                    "banking_fraud": "internet-banking-related-fraud",
                    "sim_swap_fraud": "debit-credit-card-sim-swap-fraud",
                    "whatsapp_hijack": "cheating-by-impersonation",
                    "social_media_takeover": "profile-hacking-identity-theft",
                    "phishing_scam": "e-mail-phishing",
                    "qr_code_scam": "e-wallet-related-fraud",
                    "remote_access_scam": "unauthorised-access-data-breach",
                    "mobile_hacking_malware": "damage-to-computer-systems",
                    "investment_scam": "demat-depository-fraud",
                    "job_scam": "online-job-fraud",
                    "ecommerce_fraud": "any-other-cyber-crime",
                    "sextortion": "cyber-bullying-stalking-sexting",
                    "cyberbullying_harassment": "cyber-bullying-stalking-sexting",
                    "identity_theft": "profile-hacking-identity-theft",
                    "uncategorized_other": "any-other-cyber-crime",
                }
                portal_id = EVAL_TO_PORTAL_MAP.get(case.matched_category_id)
                if portal_id:
                    subcats = get_all_subcategories()
                    sub = next((s for s in subcats if s["id"] == portal_id), None)
                    if sub:
                        res_classification = {
                            "category_id": sub["category_id"],
                            "category_name": "Cybercrime",
                            "subcategory_id": sub["id"],
                            "subcategory_name": sub["name"],
                            "match_confidence": case.match_confidence,
                            "needs_confirmation": False
                        }
            
            return {
                "messages": messages,
                "stage": "stage_4_evidence" if is_complete else "stage_3_followup",
                "classification": res_classification,
                "followup_answers": res_followup_answers,
                "remaining_questions": [],
                "summary": case.summary,
                "timeline": case.timeline,
                "summary_generated": is_complete,
                "evidence": res_evidence
            }

        # 2. Run Triage on the first message
        triage_notice = None
        if case.phase == "TRIAGE" and not case.urgent_notice_shown:
            signal = detect_financial_loss_regex(user_input)
            if signal == "ambiguous":
                try:
                    financial_loss = detect_financial_loss_llm(user_input, call_groq)
                except Exception:
                    financial_loss = True
            else:
                financial_loss = signal == "yes"

            case.financial_loss = financial_loss
            case.urgent_notice_shown = True
            case.phase = "INTERVIEWING"

            triage_notice = build_triage_notice(financial_loss)

        # 3. Clean history for LLM
        history = []
        for m in messages:
            history.append({"role": m["role"], "content": m["content"]})
        history.append({"role": "user", "content": user_input})

        # 4. Load Prompts
        evaluation_matrix = load_evaluation_matrix()
        agent_prompt = load_agent_prompt(evaluation_matrix)
        verifier_prompt = load_verifier_prompt(evaluation_matrix)

        # Prepend system prompt for Agent call
        agent_messages = [{"role": "system", "content": agent_prompt}] + history

        # Call Agent and Verifier in parallel to minimize latency
        import time
        t_start = time.time()
        print("--- CHAT HANDLER: Calling verifier ---")
        
        verifier_output, _ = await asyncio.to_thread(call_verifier, verifier_prompt, history, {})
        
        print(f"--- CHAT HANDLER: Verifier returned in {time.time() - t_start:.2f} seconds ---")
        print("--- CHAT HANDLER: Verifier returned status:", verifier_output["status"], "---")

        # Apply verifier output
        case.apply_verifier_output(verifier_output)

        is_complete = False
        last_verifier_status = verifier_output["status"]

        if last_verifier_status == "verified":
            print("--- CHAT HANDLER: Calling agent (completion pass) ---")
            completion_feedback = {
                **verifier_output,
                "feedback_to_investigator": (
                    "The evidence is verified as report-ready. Produce the final case "
                    "summary, timeline, evidence available, unknown details, and "
                    "immediate next steps using a calm, supportive tone."
                )
            }
            agent_output, raw_reply = await asyncio.to_thread(call_agent, agent_messages, completion_feedback)
            print("--- CHAT HANDLER: Agent (completion pass) returned successfully ---")
            is_complete = True
            case.phase = "REPORT_READY"
        else:
            print("--- CHAT HANDLER: Calling agent (investigation pass) ---")
            agent_output, raw_reply = await asyncio.to_thread(call_agent, agent_messages, verifier_output)
            print("--- CHAT HANDLER: Agent (investigation pass) returned successfully ---")
            is_complete = False
            case.phase = "INTERVIEWING"

        # Update CaseState summary and timeline from agent outputs
        if agent_output.get("summary"):
            case.summary = agent_output["summary"]
        if isinstance(agent_output.get("timeline"), list):
            case.timeline = agent_output["timeline"]

        # 5. Build final reply text
        reply_text = agent_output["reply"]
        if triage_notice:
            reply_text = f"{triage_notice}\n\n{reply_text}"

        # 6. Build response state
        res_classification = classification
        if case.matched_category_id:
            from utils.classification_mapper import get_all_subcategories
            EVAL_TO_PORTAL_MAP = {
                "upi_fraud": "upi-related-frauds",
                "banking_fraud": "internet-banking-related-fraud",
                "sim_swap_fraud": "debit-credit-card-sim-swap-fraud",
                "whatsapp_hijack": "cheating-by-impersonation",
                "social_media_takeover": "profile-hacking-identity-theft",
                "phishing_scam": "e-mail-phishing",
                "qr_code_scam": "e-wallet-related-fraud",
                "remote_access_scam": "unauthorised-access-data-breach",
                "mobile_hacking_malware": "damage-to-computer-systems",
                "investment_scam": "demat-depository-fraud",
                "job_scam": "online-job-fraud",
                "ecommerce_fraud": "any-other-cyber-crime",
                "sextortion": "cyber-bullying-stalking-sexting",
                "cyberbullying_harassment": "cyber-bullying-stalking-sexting",
                "identity_theft": "profile-hacking-identity-theft",
                "uncategorized_other": "any-other-cyber-crime",
            }
            
            portal_id = EVAL_TO_PORTAL_MAP.get(case.matched_category_id)
            if portal_id:
                subcats = get_all_subcategories()
                sub = next((s for s in subcats if s["id"] == portal_id), None)
                if sub:
                    res_classification = {
                        "category_id": sub["category_id"],
                        "category_name": "Cybercrime",
                        "subcategory_id": sub["id"],
                        "subcategory_name": sub["name"],
                        "match_confidence": case.match_confidence,
                        "needs_confirmation": False
                    }
            else:
                cat = CATEGORIES.get(case.matched_category_id)
                if cat:
                    res_classification = {
                        "category_id": case.matched_category_id,
                        "category_name": "Cybercrime",
                        "subcategory_id": case.matched_category_id,
                        "subcategory_name": cat.display_name,
                        "match_confidence": case.match_confidence,
                        "needs_confirmation": False
                    }

        res_evidence = {k: bool(v) for k, v in case.evidence_status.items()}

        res_followup_answers = {**case.followup_answers}
        res_followup_answers["_triage_financial_loss"] = "true" if case.financial_loss else "false"
        res_followup_answers["_triage_urgent_notice_shown"] = "true" if case.urgent_notice_shown else "false"
        res_followup_answers["_triage_phase"] = case.phase

        # Build assistant message object
        assistant_msg = {
            "role": "assistant",
            "content": reply_text,
            "type": "evidence_checklist" if is_complete else "text",
            "options": []
        }

        # Update message history
        messages.append({"role": "user", "content": user_input, "type": "text"})
        messages.append(assistant_msg)

        return {
            "messages": messages,
            "stage": "stage_4_evidence" if is_complete else "stage_3_followup",
            "classification": res_classification,
            "followup_answers": res_followup_answers,
            "remaining_questions": [],
            "summary": case.summary,
            "timeline": case.timeline,
            "summary_generated": is_complete,
            "evidence": res_evidence
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe")
async def api_transcribe(file: UploadFile = File(...)):
    """Transcribe uploaded audio file using Groq Whisper model."""
    try:
        file_bytes = await file.read()
        filename = file.filename or "audio.webm"
        from utils.groq_client import transcribe_audio
        text = transcribe_audio(file_bytes, filename)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-summary")

async def api_generate_summary(req: SummaryRequest):
    """Generate case summary and timeline via AI models."""
    case_data = {
        "incident_description": req.incident_description,
        "classification": req.classification,
        "followup_answers": req.followup_answers,
        "evidence_collected": req.evidence,
    }
    res = generate_summary_and_timeline(case_data)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@app.post("/api/export/pdf")
async def export_pdf(case_data: Dict[str, Any]):
    """Compile PDF and stream the download."""
    try:
        pdf_bytes = generate_pdf_report(case_data)
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=CFRO_FIR.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export/txt")
async def export_txt(case_data: Dict[str, Any]):
    """Compile plain TXT complaint and stream the download."""
    try:
        txt_str = generate_complaint_package_text(case_data)
        return StreamingResponse(
            io.BytesIO(txt_str.encode("utf-8")),
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=CFRO_Complaint.txt"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export/md")
async def export_md(case_data: Dict[str, Any]):
    """Compile Markdown summary and stream the download."""
    try:
        md_str = generate_complaint_package_markdown(case_data)
        return StreamingResponse(
            io.BytesIO(md_str.encode("utf-8")),
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=CFRO_Report.md"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export/html")
async def export_html(case_data: Dict[str, Any]):
    """Compile printable layout summary view."""
    try:
        html_str = generate_printable_summary_html(case_data)
        return HTMLResponse(
            content=html_str,
            headers={"Content-Disposition": "attachment; filename=CFRO_Print.html"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
