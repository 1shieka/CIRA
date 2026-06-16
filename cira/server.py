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
    """Handle chat message logic and stage transitions via dynamic AI investigation."""
    messages = list(req.messages)
    stage = req.stage
    classification = req.classification
    followup_answers = dict(req.followup_answers)
    evidence = dict(req.evidence)
    user_input = req.user_input
    summary = req.summary or ""
    timeline = list(req.timeline) if req.timeline else []

    # Call dynamic AI Investigator
    result = investigate_incident(
        messages=messages,
        stage=stage,
        classification=classification,
        followup_answers=followup_answers,
        evidence=evidence,
        timeline=timeline,
        summary=summary,
        user_input=user_input,
    )

    if "error" in result:
        # Fallback in case of error
        messages.append({"role": "user", "content": user_input, "type": "text"})
        messages.append({
            "role": "assistant",
            "content": f"I experienced an issue processing that: {result['error']}. Let's continue describing the details.",
            "type": "text"
        })
        return {
            "messages": messages,
            "stage": stage,
            "classification": classification,
            "followup_answers": followup_answers,
            "remaining_questions": [],
            "summary": summary,
            "timeline": timeline,
            "summary_generated": False,
        }

    # Extract dynamic state from AI response
    stage = result.get("stage", stage)
    classification = result.get("classification", classification)
    followup_answers = result.get("followup_answers", followup_answers)
    timeline = result.get("timeline", timeline)
    summary = result.get("summary", summary)
    evidence = result.get("evidence", evidence)
    summary_generated = result.get("summary_generated", False)

    assistant_msg = result.get("assistant_message")
    if assistant_msg:
        # Append user input and then assistant message
        messages.append({"role": "user", "content": user_input, "type": "text"})
        messages.append(assistant_msg)

    return {
        "messages": messages,
        "stage": stage,
        "classification": classification,
        "followup_answers": followup_answers,
        "remaining_questions": [],
        "summary": summary,
        "timeline": timeline,
        "summary_generated": summary_generated,
        "evidence": evidence
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
