"""Standalone CIRA investigation agent loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.azure_openai_client import (
    AZURE_OPENAI_DEPLOYMENT,
    call_azure_openai,
    extract_json,
)


AGENT_PROMPT_PATH = Path(__file__).with_name("agent.md")
VERIFIER_PROMPT_PATH = Path(__file__).with_name("verifier.md")
EVALUATION_PATH = Path(__file__).with_name("EVALUATION.md")


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
        prompt_messages.append(
            {
                "role": "user",
                "content": (
                    "Internal verifier feedback. Use this to produce the next "
                    "user-facing Investigation Officer reply. Do not mention the "
                    "verifier, scores, or internal policy. Ask exactly one short "
                    "question for the missing evidence, gently and specifically.\n\n"
                    f"{json.dumps(verifier_feedback, ensure_ascii=False, indent=2)}"
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
        reply = "I am here with you. What happened?"

    return {"status": status, "reply": reply.strip()}, raw


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
            "Ask exactly one focused question for the highest-priority missing "
            "evidence required by the matched category in EVALUATION.md."
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


def run_loop() -> None:
    """Run an interactive terminal loop for the Investigation Officer."""
    evaluation_matrix = load_evaluation_matrix()
    system_prompt = load_agent_prompt(evaluation_matrix)
    verifier_prompt = load_verifier_prompt(evaluation_matrix)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    print("CIRA Investigation Officer")
    print(f"Azure OpenAI deployment: {AZURE_OPENAI_DEPLOYMENT}")
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
            print("Case reset. Please describe the incident again.\n")
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            agent_output, raw_reply = call_agent(messages)
            verifier_output, _ = call_verifier(
                verifier_prompt,
                messages,
                agent_output,
            )

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
            else:
                agent_output, raw_reply = call_agent(messages, verifier_output)
                agent_output["status"] = "investigating"
        except Exception as exc:
            print(f"\nInvestigation Officer: Agent error: {exc}\n")
            continue

        messages.append({"role": "assistant", "content": raw_reply})
        reply = agent_output["reply"]
        print(f"\nInvestigation Officer: {reply}\n")

        if agent_output["status"] == "complete":
            print("Investigation complete.")
            break


if __name__ == "__main__":
    run_loop()
