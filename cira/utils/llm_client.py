"""LLM helpers for incident understanding and summary generation."""

import json

from utils.azure_openai_client import AZURE_OPENAI_DEPLOYMENT, call_azure_openai_json

LLM_MODEL = AZURE_OPENAI_DEPLOYMENT


def _safe_llm_json_call(prompt: str) -> dict:
    """Call the configured model and return parsed JSON, or an error dict."""
    try:
        return call_azure_openai_json(prompt)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            return {"error": "Azure OpenAI API rate limit reached. Please wait and try again."}
        if "API key" in err or "401" in err or "403" in err or "invalid" in err.lower():
            return {"error": "Invalid or unauthorized AZURE_OPENAI_API_KEY."}
        return {"error": f"Azure OpenAI API error: {err}"}


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
    result = _safe_llm_json_call(prompt)
    if "error" in result:
        return result

    required = {"summary", "suggested_category", "confidence"}
    if not required.issubset(result.keys()):
        return {"error": "Incomplete response from Azure OpenAI.", "raw": result}

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
    result = _safe_llm_json_call(prompt)
    if "error" in result:
        return result

    if "summary" not in result or "timeline" not in result:
        return {"error": "Incomplete summary/timeline from Azure OpenAI.", "raw": result}

    return {
        "summary": result["summary"],
        "timeline": result.get("timeline", []),
    }
