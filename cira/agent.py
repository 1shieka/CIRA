"""Standalone CIRA investigation agent loop.

Flow:
  TRIAGE          -> one-time financial-loss check on the first user message,
                     surfaces the golden-hour advisory immediately if relevant
  INTERVIEWING    -> existing agent <-> verifier loop, now also accumulating
                     structured CaseState (evidence, timeline, facts) so the
                     final report doesn't depend on the model re-deriving
                     everything from scratch
  REPORT_READY    -> verifier says evidence is report-ready; agent produces
                     the final summary
  AWAITING_FIR    -> offer / confirm PDF generation
  FIR_GENERATED   -> PDF written to disk

The user can also say "generate the FIR" / "make the report" at ANY point,
in any phase — this is checked every turn before normal phase logic runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from utils.groq_client import (
    GROQ_MODEL,
    call_groq as call_azure_openai,
    extract_json,
)
from utils.pdf_generator import generate_pdf_report

from case_state import CaseState
from triage import (
    build_triage_notice,
    detect_financial_loss_llm,
    detect_financial_loss_regex,
)


AGENT_PROMPT_PATH = Path(__file__).with_name("agent.md")
VERIFIER_PROMPT_PATH = Path(__file__).with_name("verifier.md")
EVALUATION_PATH = Path(__file__).with_name("EVALUATION.md")

GENERATE_FIR_PATTERNS = [
    r"\bgenerate\b.{0,20}\b(fir|report|pdf)\b",
    r"\b(make|create|build)\b.{0,20}\b(fir|report|pdf)\b",
    r"\bfir\b.{0,15}\bnow\b",
    r"\bdownload\b.{0,15}\b(report|fir|pdf)\b",
]

PROCEED_ANYWAY_PATTERNS = [
    r"\bproceed anyway\b",
    r"\bgenerate (it )?anyway\b",
    r"\bjust generate\b",
    r"\bgo ahead\b.{0,15}\b(anyway|now)\b",
    r"\bi (don'?t|do not) have (more|any more|anything else)\b",
]


def wants_fir_generation(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in GENERATE_FIR_PATTERNS)


def wants_to_proceed_anyway(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in PROCEED_ANYWAY_PATTERNS)


def load_evaluation_matrix() -> str:
    """Load the evidence evaluation matrix without modifying it."""
    return EVALUATION_PATH.read_text(encoding="utf-8")


def build_prompt(prompt_path: Path, evaluation_matrix: str) -> str:
    """Build an agent prompt with the shared evidence matrix as read-only context."""
    base_prompt = prompt_path.read_text(encoding="utf-8")
    return (
        f"{base_prompt}\n\n"
        "## Read-Only Evidence Evaluation Reference\n\n"
        "Use the following EVALUATION.md content as the evidence criteria source. "
        "Do not rewrite it, do not claim it is complete unless the user's evidence "
        "satisfies its rules, and keep user-facing language gentle.\n\n"
        f"{evaluation_matrix}"
    )


def load_agent_prompt(evaluation_matrix: str) -> str:
    """Load the Investigation Officer prompt with evidence criteria context."""
    return build_prompt(AGENT_PROMPT_PATH, evaluation_matrix)


def load_verifier_prompt(evaluation_matrix: str) -> str:
    """Load the Evidence Verifier prompt with evidence criteria context."""
    return build_prompt(VERIFIER_PROMPT_PATH, evaluation_matrix)


def call_agent(
    messages: list[dict[str, str]],
    verifier_feedback: dict[str, Any] | None = None,
) -> tuple[dict[str, str], str]:
    """Send the conversation to Azure OpenAI and return parsed agent output plus raw text."""
    prompt_messages = [*messages]
    if verifier_feedback:
        feedback_str = verifier_feedback.get("feedback_to_investigator", "")
        prompt_messages.append(
            {
                "role": "user",
                "content": (
                    "Internal verifier feedback/instruction:\n"
                    f"\"{feedback_str}\"\n\n"
                    "Do NOT mention the verifier, internal scores, or policy. "
                    "You MUST ask ONLY ONE focused question corresponding to this feedback. "
                    "Do not dump multiple questions or ask for multiple pieces of evidence at once."
                ),
            }
        )

    raw = call_azure_openai(prompt_messages, temperature=0.25)
    try:
        parsed = extract_json(raw)
    except ValueError:
        parsed = {
            "status": "investigating",
            "reply": raw,
        }

    status = parsed.get("status", "investigating")
    reply = parsed.get("reply", "")
    if status not in {"investigating", "complete"}:
        status = "investigating"
    if not isinstance(reply, str) or not reply.strip():
        reply = "Please describe what happened, including when it happened and what account, app, bank, website, or device was involved."

    return {
        "status": status,
        "reply": reply.strip(),
        "summary": parsed.get("summary", ""),
        "timeline": parsed.get("timeline", []),
    }, raw


def call_verifier(
    verifier_prompt: str,
    conversation: list[dict[str, str]],
    investigator_output: dict[str, str],
) -> tuple[dict[str, Any], str]:
    """Verify whether the user's evidence satisfies EVALUATION.md criteria."""
    case_messages = [
        message for message in conversation if message.get("role") != "system"
    ]
    payload = {
        "conversation": case_messages,
        "investigator_output": investigator_output,
    }
    raw = call_azure_openai(
        [
            {"role": "system", "content": verifier_prompt},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, indent=2),
            },
        ],
        temperature=0.1,
    )

    try:
        parsed = extract_json(raw)
    except ValueError:
        parsed = {
            "status": "needs_more_information",
            "matched_categories": [],
            "missing_required_evidence": [],
            "critical_missing_flags": [],
            "feedback_to_investigator": (
                "The evidence verification could not be parsed. Ask the user for "
                "the core incident timeline, affected account/platform, and any "
                "screenshots, transaction IDs, URLs, phone numbers, or messages."
            ),
        }

    status = parsed.get("status", "needs_more_information")
    if status not in {"verified", "needs_more_information"}:
        status = "needs_more_information"

    feedback = parsed.get("feedback_to_investigator", "")
    if not isinstance(feedback, str) or not feedback.strip():
        feedback = (
            "Ask ONLY ONE focused question for the missing evidence required "
            "by the matched category in EVALUATION.md."
        )

    return {
        "status": status,
        "matched_categories": parsed.get("matched_categories", []),
        "evidence_completeness": parsed.get("evidence_completeness", {}),
        "collected_required_evidence": parsed.get(
            "collected_required_evidence", []
        ),
        "missing_required_evidence": parsed.get("missing_required_evidence", []),
        "critical_missing_flags": parsed.get("critical_missing_flags", []),
        "feedback_to_investigator": feedback.strip(),
    }, raw


def handle_fir_generation_request(
    case: CaseState,
    verifier_status: str | None,
    user_confirmed_partial: bool,
) -> tuple[str | None, bytes | None]:
    """Decide whether to generate the PDF now, or ask the user to confirm a
    partial/incomplete report first. Returns (message_to_user, pdf_bytes).
    Exactly one of the two will be non-None, unless the user has not yet
    confirmed and we are waiting (in which case message is set, bytes is None).
    """
    is_ready = verifier_status == "verified"

    if is_ready or user_confirmed_partial:
        case_data = case.to_pdf_case_data()
        pdf_bytes = generate_pdf_report(case_data)
        if is_ready:
            return (
                "Your case report is ready. I've compiled everything we discussed "
                "into the FIR document below.",
                pdf_bytes,
            )
        missing = case.missing_required_labels()
        missing_note = (
            f" Missing items noted in the report as pending: {', '.join(missing)}."
            if missing
            else ""
        )
        return (
            "Generating your report now as requested, marked as an incomplete "
            f"investigation.{missing_note} You can ask me to regenerate it later "
            "once you have more details.",
            pdf_bytes,
        )

    missing = case.missing_required_labels()
    missing_note = (
        f" Specifically: {', '.join(missing)}." if missing else ""
    )
    return (
        "I can generate the report now, but providing a bit more detail first "
        "will make your case stronger and more presentable to investigators."
        f"{missing_note} Want to add more, or should I proceed with what we "
        "have? (Say \"proceed anyway\" to generate it now.)",
        None,
    )


def run_loop() -> None:
    """Run an interactive terminal loop for the Investigation Officer."""
    evaluation_matrix = load_evaluation_matrix()
    system_prompt = load_agent_prompt(evaluation_matrix)
    verifier_prompt = load_verifier_prompt(evaluation_matrix)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    case = CaseState()
    last_verifier_status: str | None = None
    awaiting_partial_confirmation = False

    print("CIRA Investigation Officer")
    print(f"Groq Model: {GROQ_MODEL}")
    print("Describe the cyber incident. Type /reset to start over or /exit to quit.\n")

    while True:
        try:
            user_input = input("User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() in {"/exit", "exit", "quit", "/quit"}:
            print("Exiting.")
            break

        if user_input.lower() == "/reset":
            messages = [{"role": "system", "content": system_prompt}]
            case = CaseState()
            last_verifier_status = None
            awaiting_partial_confirmation = False
            print("Case reset. Please describe the incident again.\n")
            continue

        # --- TRIAGE: runs once, on the first real user message only ---
        if case.phase == "TRIAGE" and not case.urgent_notice_shown:
            signal = detect_financial_loss_regex(user_input)
            if signal == "ambiguous":
                try:
                    financial_loss = detect_financial_loss_llm(user_input, call_azure_openai)
                except Exception:
                    financial_loss = True  # fail safe: show the advisory
            else:
                financial_loss = signal == "yes"

            case.financial_loss = financial_loss
            case.urgent_notice_shown = True
            case.phase = "INTERVIEWING"

            notice = build_triage_notice(financial_loss)
            if notice:
                print(f"\nInvestigation Officer:\n{notice}\n")

        # --- Mid-conversation FIR generation command (any phase) ---
        if wants_fir_generation(user_input):
            confirmed_partial = (
                awaiting_partial_confirmation and wants_to_proceed_anyway(user_input)
            )
            message, pdf_bytes = handle_fir_generation_request(
                case, last_verifier_status, confirmed_partial
            )
            print(f"\nInvestigation Officer: {message}\n")
            if pdf_bytes is not None:
                out_path = Path("case_report.pdf")
                out_path.write_bytes(pdf_bytes)
                print(f"(Saved to {out_path.resolve()})\n")
                case.phase = "FIR_GENERATED"
                awaiting_partial_confirmation = False
                continue
            else:
                awaiting_partial_confirmation = True
                continue

        if wants_to_proceed_anyway(user_input) and awaiting_partial_confirmation:
            message, pdf_bytes = handle_fir_generation_request(
                case, last_verifier_status, user_confirmed_partial=True
            )
            print(f"\nInvestigation Officer: {message}\n")
            if pdf_bytes is not None:
                out_path = Path("case_report.pdf")
                out_path.write_bytes(pdf_bytes)
                print(f"(Saved to {out_path.resolve()})\n")
                case.phase = "FIR_GENERATED"
            awaiting_partial_confirmation = False
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            agent_output, raw_reply = call_agent(messages)
            verifier_output, _ = call_verifier(
                verifier_prompt,
                messages,
                agent_output,
            )
            last_verifier_status = verifier_output["status"]
            case.apply_verifier_output(verifier_output)

            if verifier_output["status"] == "verified":
                if agent_output["status"] != "complete":
                    agent_output, raw_reply = call_agent(
                        messages,
                        {
                            **verifier_output,
                            "feedback_to_investigator": (
                                "The evidence is verified as report-ready. Produce "
                                "the final case summary, timeline, evidence "
                                "available, unknown details, and immediate next "
                                "steps using a calm, supportive tone."
                            ),
                        },
                    )
                    agent_output["status"] = "complete"
                case.phase = "REPORT_READY"
            else:
                agent_output, raw_reply = call_agent(messages, verifier_output)
                agent_output["status"] = "investigating"
        except Exception as exc:
            print(f"\nInvestigation Officer: Agent error: {exc}\n")
            continue

        messages.append({"role": "assistant", "content": raw_reply})
        if agent_output.get("summary"):
            case.summary = agent_output["summary"]
        if isinstance(agent_output.get("timeline"), list):
            case.timeline = agent_output["timeline"]

        reply = agent_output["reply"]
        print(f"\nInvestigation Officer: {reply}\n")

        if agent_output["status"] == "complete":
            print(
                "Investigation complete. Say \"generate the FIR\" whenever you're "
                "ready for the PDF report."
            )


if __name__ == "__main__":
    run_loop()
