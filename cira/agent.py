"""Standalone CIRA investigation agent loop."""

from __future__ import annotations

from pathlib import Path

from utils.azure_openai_client import (
    AZURE_OPENAI_DEPLOYMENT,
    call_azure_openai,
    extract_json,
)


AGENT_PROMPT_PATH = Path(__file__).with_name("agent.md")


def load_agent_prompt() -> str:
    """Load the Investigation Officer prompt from agent.md."""
    return AGENT_PROMPT_PATH.read_text(encoding="utf-8")


def call_agent(messages: list[dict[str, str]]) -> tuple[dict[str, str], str]:
    """Send the conversation to Azure OpenAI and return parsed agent output plus raw text."""
    raw = call_azure_openai(messages, temperature=0.25)
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

    return {"status": status, "reply": reply.strip()}, raw


def run_loop() -> None:
    """Run an interactive terminal loop for the Investigation Officer."""
    system_prompt = load_agent_prompt()
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
