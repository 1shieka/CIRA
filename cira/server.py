"""FastAPI Backend Server for CFRO."""

import json
from pathlib import Path
import io
import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

from utils.llm_client import understand_incident, generate_summary_and_timeline
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
    """Handle chat message logic and stage transitions."""
    messages = list(req.messages)
    stage = req.stage
    classification = req.classification
    followup_answers = dict(req.followup_answers)
    remaining_questions = list(req.remaining_questions)
    evidence = dict(req.evidence)
    user_input = req.user_input

    # Add user message to history
    messages.append({"role": "user", "content": user_input, "type": "text"})

    summary = ""
    timeline = []
    summary_generated = False

    # Stage 1: Intake -> Stage 2: Classification
    if stage == "stage_1_intake":
        incident_description = user_input
        stage = "stage_2_classification"
        
        # Call AI understanding
        result = understand_incident(user_input, get_subcategory_names())
        
        if "error" in result:
            messages.append({
                "role": "assistant",
                "content": "I couldn't reach the classification engine right now. Please select the correct category in the Case File panel or tell me more about it.",
                "type": "text"
            })
            stage = "stage_2_confirming"
        else:
            mapped = map_to_official_category(result)
            classification = mapped
            subcat_name = mapped.get("subcategory_name")
            cat_name = mapped.get("category_name")
            confidence_low = mapped.get("needs_confirmation")

            if not confidence_low:
                # Set up subcategory select
                subcategory_id = mapped.get("subcategory_id")
                remaining_questions = get_followup_questions(subcategory_id, followup_answers)
                
                messages.append({
                    "role": "assistant",
                    "content": f"Understood. This looks like **{subcat_name}** under *{cat_name}*. I've loaded the incident playbook on the right. Let me ask a few quick questions to build your case file.",
                    "type": "text"
                })
                stage = "stage_3_followup"

                if remaining_questions:
                    next_q = remaining_questions[0]
                    messages.append({
                        "role": "assistant",
                        "content": next_q["text"],
                        "type": "quick_reply" if next_q["type"] == "select" else "text",
                        "options": next_q.get("options", [])
                    })
                else:
                    stage = "stage_4_evidence"
                    messages.append({
                        "role": "assistant",
                        "content": "No further questions needed. Here is your evidence checklist — please tick what you have preserved:",
                        "type": "evidence_checklist"
                    })
            else:
                stage = "stage_2_confirming"
                messages.append({
                    "role": "assistant",
                    "content": f"I think this fits **{subcat_name}** under *{cat_name}*, but I want to confirm. Which of these best describes your situation?",
                    "type": "quick_reply",
                    "options": [subcat_name, "UPI Related Frauds", "Online Job Fraud", "Manual Override / Choose Other..."]
                })

    # Stage 2 Confirming quick-replies (e.g. selection)
    elif stage == "stage_2_confirming":
        if user_input == "Manual Override / Choose Other...":
            messages.append({
                "role": "assistant",
                "content": "No problem. Describe the incident in more detail and I will re-classify, or select the correct subcategory in the Case File panel.",
                "type": "text"
            })
        else:
            subcategories = get_all_subcategories()
            matched = next((s for s in subcategories if s["name"] == user_input), None)
            if matched:
                subcategory_id = matched["id"]
                # Perform handle_category_select operations
                meta = load_playbook(subcategory_id)
                categories_path = DATA_DIR / "categories.json"
                with open(categories_path, encoding="utf-8") as f:
                    cat_data = json.load(f)
                selected_cat = next(c for c in cat_data["categories"] if c["id"] == matched["category_id"])

                classification = {
                    "category_id": matched["category_id"],
                    "category_name": selected_cat["name"],
                    "subcategory_id": matched["id"],
                    "subcategory_name": matched["name"],
                    "match_confidence": 1.0,
                    "needs_confirmation": False,
                }
                remaining_questions = get_followup_questions(subcategory_id, followup_answers)

                messages.append({
                    "role": "assistant",
                    "content": f"Confirmed. Mapped to **{matched['name']}**. Incident Playbook and diagnostics loaded.",
                    "type": "text"
                })
                stage = "stage_3_followup"

                if remaining_questions:
                    next_q = remaining_questions[0]
                    messages.append({
                        "role": "assistant",
                        "content": next_q["text"],
                        "type": "quick_reply" if next_q["type"] == "select" else "text",
                        "options": next_q.get("options", [])
                    })
                else:
                    stage = "stage_4_evidence"
                    messages.append({
                        "role": "assistant",
                        "content": "No further questions needed. Here is your evidence checklist — please tick what you have preserved:",
                        "type": "evidence_checklist"
                    })

    # Stage 3: Followup questions
    elif stage == "stage_3_followup":
        subcategory_id = classification.get("subcategory_id") if classification else None
        if subcategory_id and remaining_questions:
            active_q = remaining_questions.pop(0)
            followup_answers[active_q["id"]] = user_input
            
            # Recalculate remaining questions
            remaining_questions = get_followup_questions(subcategory_id, followup_answers)

            if remaining_questions:
                next_q = remaining_questions[0]
                messages.append({
                    "role": "assistant",
                    "content": next_q["text"],
                    "type": "quick_reply" if next_q["type"] == "select" else "text",
                    "options": next_q.get("options", [])
                })
            else:
                stage = "stage_4_evidence"
                summary_generated = True
                
                # Pre-generate summary and timeline
                case_data = {
                    "incident_description": messages[1]["content"] if len(messages) > 1 else "",
                    "classification": classification,
                    "followup_answers": followup_answers,
                    "evidence_collected": evidence,
                }
                res = generate_summary_and_timeline(case_data)
                if "error" not in res:
                    summary = res.get("summary", "")
                    timeline = res.get("timeline", [])

                messages.append({
                    "role": "assistant",
                    "content": "All follow-up questions completed. I've compiled your Case File. Please tick items as you secure evidence:",
                    "type": "evidence_checklist"
                })

    return {
        "messages": messages,
        "stage": stage,
        "classification": classification,
        "followup_answers": followup_answers,
        "remaining_questions": remaining_questions,
        "summary": summary,
        "timeline": timeline,
        "summary_generated": summary_generated,
    }

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
