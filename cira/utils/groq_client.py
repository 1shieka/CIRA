"""Groq API client for incident understanding and summary generation."""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

# Model name — change here if needed
GROQ_MODEL = "llama-3.3-70b-versatile"

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_client: Groq | None = None


def _get_api_key() -> str | None:
    return os.getenv("GROQ_API_KEY")


def _ensure_client() -> Groq:
    global _client
    api_key = _get_api_key()
    if not api_key or api_key == "your_key_here":
        raise ValueError(
            "GROQ_API_KEY is missing or not set. Copy .env.example to .env and add your key."
        )
    if _client is None:
        _client = Groq(api_key=api_key)
    return _client


def _extract_json(text: str) -> dict:
    """Extract JSON object from model response, handling markdown fences."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            return json.loads(brace_match.group())
        raise ValueError(f"Could not parse JSON from model response: {text[:200]}")


def _safe_groq_call(prompt: str) -> dict:
    """Call Groq and return parsed JSON, or error dict on failure."""
    try:
        client = _ensure_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        if not content:
            return {"error": "Empty response from Groq API."}
        return _extract_json(content)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            return {"error": "Groq API rate limit reached. Please wait and try again."}
        if "API key" in err or "401" in err or "403" in err or "invalid" in err.lower():
            return {"error": "Invalid or unauthorized GROQ_API_KEY."}
        return {"error": f"Groq API error: {err}"}


def understand_incident(user_text: str, category_list: list[str]) -> dict:
    """
    Analyze victim's account and suggest an official subcategory.

    Returns dict with keys: summary, suggested_category, confidence
    Or: error key on failure
    """
    categories_formatted = "\n".join(f"- {name}" for name in category_list)
    prompt = f"""You are CIRA (Cyber Incidence Response Assistant) helping cybercrime victims in India.

The victim describes their incident:
\"\"\"
{user_text}
\"\"\"

Official subcategory names (choose exactly one):
{categories_formatted}

Respond with ONLY valid JSON (no markdown):
{{
  "summary": "2-3 sentence plain-language summary of what happened",
  "suggested_category": "exact subcategory name from the list above",
  "confidence": "high" | "medium" | "low"
}}

Use confidence:
- high: clear match to one subcategory
- medium: likely match but some ambiguity
- low: unclear or could fit multiple categories
"""
    result = _safe_groq_call(prompt)
    if "error" in result:
        return result

    required = {"summary", "suggested_category", "confidence"}
    if not required.issubset(result.keys()):
        return {"error": "Incomplete response from Groq.", "raw": result}

    return {
        "summary": result["summary"],
        "suggested_category": result["suggested_category"],
        "confidence": result.get("confidence", "low"),
    }


def generate_summary_and_timeline(case_data: dict) -> dict:
    """
    Generate editable case summary and timeline from full case data.

    case_data should include: incident description, classification, follow-up answers.
    Returns: {summary, timeline: [{time, event}, ...]} or {error: ...}
    """
    prompt = f"""You are CIRA generating a case summary and timeline for a cybercrime victim in India.

Full case data (JSON):
{json.dumps(case_data, indent=2, default=str)}

Create a clear, victim-friendly summary and chronological timeline for reporting on cybercrime.gov.in.

Respond with ONLY valid JSON:
{{
  "summary": "Structured paragraph summarizing the incident, losses, and key facts",
  "timeline": [
    {{"time": "approximate date/time or order", "event": "what happened"}},
    ...
  ]
}}
"""
    result = _safe_groq_call(prompt)
    if "error" in result:
        return result

    if "summary" not in result or "timeline" not in result:
        return {"error": "Incomplete summary/timeline from Groq.", "raw": result}

    return {
        "summary": result["summary"],
        "timeline": result.get("timeline", []),
    }


def investigate_incident(
    messages: list[dict],
    stage: str,
    classification: dict | None,
    followup_answers: dict,
    evidence: dict[str, bool],
    timeline: list[dict],
    summary: str,
    user_input: str,
) -> dict:
    """
    Run the dynamic investigator session via Groq.
    Acts as a Cyber First Response Officer (intake officer).
    """
    try:
        categories_path = Path(__file__).resolve().parent.parent / "data" / "categories.json"
        with open(categories_path, encoding="utf-8") as f:
            categories_data = json.load(f)
    except Exception:
        categories_data = {}

    system_prompt = f"""You are the Cyber First Response Officer (case intake officer) for CIRA, the Cyber Incidence Response Assistant for cybercrime victims in India.

Your primary objectives are to:
1. Reassure, support, and guide the victim calmly, respectfully, and professionally. Never blame or shame them.
2. Build an FIR-ready complaint package.
3. Inform the victim that their data is private, secure, and remains inside this workspace.
4. Advise on immediate actions (like calling 1930 and reporting on cybercrime.gov.in) to stop losses and maximize recovery.
5. Explain how the scam worked (scam model, social engineering, warning signs, remaining risks) once sufficient information is gathered.

---

### STAGE-SPECIFIC BEHAVIOR RULES:

1. **Intake / First Response (If stage is "stage_1_intake" or this is the first assistant turn):**
   - You MUST:
     1. Summarize your understanding of the user's description.
     2. Reassure the victim that their data is private and remains in this workspace.
     3. Encourage prompt reporting.
     4. Explain that quick action (especially calling 1930 or reporting to the cybercrime portal) improves recovery/intervention in financial frauds.
     5. State the likely official subcategory of the cybercrime from the category list below and specify your confidence level.
   - Example Response:
     "Thank you for sharing that. From what you've described, this appears to be an Online Job Fraud incident. Your information remains within this case workspace and we will only collect information needed to help prepare a cybercrime complaint. If money was lost recently, reporting quickly through 1930 and the National Cyber Crime Portal can improve the chances of intervention and recovery. Before we proceed, I'd like to gather a few important details."
   - Transition stage to "stage_3_followup".

2. **Investigation / Follow-up ("stage_3_followup"):**
   - Continuously determine what information is missing from the case file.
   - Ask **only 1 to 3 focused questions** per turn. Do not dump a list of 10 questions.
   - Gather:
     - Incident Narrative (attacker's claims, victim's belief, sequence of events).
     - Timeline (approximate dates, times).
     - Suspect contact details (phone, UPI ID, telegram, Instagram, website, bank account, crypto wallet).
     - Platform involved (WhatsApp, Instagram, Telegram, bank, mobile app).
     - Victim actions (clicks, downloads, installations, payments made).
     - Financial info (loss amount, bank, UPI app, UTR numbers / reference IDs).
     - Account/Device impact (access lost, malware, device compromise).
   - **SECURITY RULE**: Never ask for PINs, passwords, OTPs, CVVs, seed phrases, or private keys.
    - Progressively update the `timeline` array (e.g. `[[{{"time": "...", "event": "..."}}]]`) and write/update the incident `summary` (draft summary of the event) as the user shares info.
    - Auto-detect evidence items based on the conversation and check them in the `evidence` dictionary (e.g., `{{\"transaction_records\": true}}`). Only ask about evidence that is not yet identified.
   - Once enough information is gathered:
     - Explain clearly how the scam worked, why they were targeted, the social engineering techniques used, the warning signs, and remaining risks.
     - Transition to "stage_4_evidence" and set `summary_generated` to true.
     - Respond with a message showing the evidence checklist (type: "evidence_checklist").

3. **Decision Rule before generating final package:**
   - Before setting `summary_generated` to true and completing, ask yourself: "Do I have enough information for an investigator to understand and act on this case?"
   - Do not generate the final summary until you have gathered: narrative, timeline, financial info (if applicable), evidence inventory, classification, and impact assessment.

---

### CATEGORIES AND SUBCATEGORIES LIST:
{json.dumps(categories_data, indent=2)}

### OFFICIAL EVIDENCE ID LIST:
- "screenshots_profiles" (for social media: fake/offending profiles or posts)
- "messages" (for social media: saved chats, comments, emails)
- "profile_urls" (for social media: URLs/usernames of involved accounts)
- "witness_info" (for social media: names/contacts of witnesses)
- "transaction_records" (for financial: bank/UPI statements or screenshots)
- "utr_references" (for financial: UTR numbers or transaction reference IDs)
- "call_sms_records" (for financial: call logs or SMS from fraudster)
- "bank_correspondence" (for financial: emails/letters from bank)
- "system_logs" (for hacking: system logs, error messages, ransom notes)
- "affected_files" (for hacking: affected files)
- "access_records" (for hacking: login history, access alerts)
- "backup_status" (for hacking: notes on backup existence)
- "general_screenshots" (for other categories: screenshots/recordings)
- "communication_records" (for other categories: messages/emails)
- "financial_records" (for other categories: payment records)
- "official_refs" (for other categories: reference numbers already filed)
- "incident_timeline" (generic: timeline)
- "identity_docs" (generic: ID documents if identity theft)
- "device_info" (generic: device models/apps involved)

---

### CURRENT STATE:
- **stage**: {stage}
- **classification**: {json.dumps(classification)}
- **followup_answers**: {json.dumps(followup_answers)}
- **timeline**: {json.dumps(timeline)}
- **summary**: {json.dumps(summary)}
- **evidence**: {json.dumps(evidence)}

### USER NEW MESSAGE:
"{user_input}"

### CHAT HISTORY (for context):
{json.dumps(messages[-10:] if len(messages) > 10 else messages)}

---

Respond with ONLY valid JSON (no markdown wrapping, no text outside JSON) in this exact format:
{{
  "stage": "current stage string",
  "classification": {{
    "category_id": "main category id",
    "category_name": "main category name",
    "subcategory_id": "subcategory id",
    "subcategory_name": "subcategory name",
    "match_confidence": 0.0 to 1.0,
    "needs_confirmation": false
  }} or null,
  "followup_answers": {{
    "key": "value"
  }},
  "timeline": [
    {{"time": "date/time", "event": "event description"}}
  ],
  "summary": "Incident summary generated so far",
  "evidence": {{
    "evidence_item_id": true
  }},
  "summary_generated": true or false,
  "assistant_message": {{
    "role": "assistant",
    "content": "Your message to the user here. If summary_generated is true, explain how the scam worked, show support, and explain the complaint package is ready below.",
    "type": "text" or "quick_reply" or "evidence_checklist",
    "options": []
  }}
}}
"""

    try:
        client = _ensure_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that only speaks in JSON schema matches.",
                },
                {"role": "user", "content": system_prompt},
            ],
            response_format={ "type": "json_object" },
        )
        content = response.choices[0].message.content
        if not content:
            return {"error": "Empty response from Groq API."}
        return _extract_json(content)
    except Exception as e:
        return {"error": f"Groq API error: {str(e)}"}


def transcribe_audio(file_bytes: bytes, filename: str) -> str:
    """Transcribe audio bytes using Groq's whisper-large-v3 model."""
    client = _ensure_client()
    transcription = client.audio.transcriptions.create(
        file=(filename, file_bytes),
        model="whisper-large-v3",
        temperature=0,
        response_format="verbose_json",
    )
    return transcription.text


