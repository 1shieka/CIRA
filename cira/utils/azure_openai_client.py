"""Azure OpenAI client helpers for CIRA language model calls."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AzureOpenAI
from dotenv import dotenv_values, load_dotenv


DEFAULT_AZURE_OPENAI_API_VERSION = "2024-12-01-preview"
DEFAULT_AZURE_OPENAI_ENDPOINT = "https://azure-foundary-a11.cognitiveservices.azure.com/"
DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-5.4-mini"
PROJECT_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
LEGACY_CIRA_ENV = Path(__file__).resolve().parents[1] / ".env"

# Retry behaviour for transient upstream errors (e.g. 429 rate limits, 5xx).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = int(os.getenv("AZURE_OPENAI_MAX_RETRIES", "4"))
RETRY_BACKOFF_SECONDS = float(os.getenv("AZURE_OPENAI_RETRY_BACKOFF", "1.5"))
MAX_RETRY_WAIT_SECONDS = 30.0


def _load_env() -> None:
    """Load repo-root .env first, then cira/.env as a compatibility fallback."""
    load_dotenv(PROJECT_ROOT_ENV, override=False)
    load_dotenv(LEGACY_CIRA_ENV, override=False)


_load_env()
AZURE_OPENAI_API_VERSION = os.getenv(
    "AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_OPENAI_API_VERSION
)
AZURE_OPENAI_ENDPOINT = os.getenv(
    "AZURE_OPENAI_ENDPOINT", DEFAULT_AZURE_OPENAI_ENDPOINT
)
AZURE_OPENAI_DEPLOYMENT = os.getenv(
    "AZURE_OPENAI_DEPLOYMENT",
    os.getenv("AZURE_OPENAI_MODEL", DEFAULT_AZURE_OPENAI_DEPLOYMENT),
)
AZURE_OPENAI_MAX_COMPLETION_TOKENS = int(
    os.getenv("AZURE_OPENAI_MAX_COMPLETION_TOKENS", "16384")
)


def _fallback_deployments() -> list[str]:
    """Comma-separated alternate Azure deployments tried after transient failures."""
    raw = os.getenv("AZURE_OPENAI_FALLBACK_DEPLOYMENTS", "")
    return [deployment.strip() for deployment in raw.split(",") if deployment.strip()]


def _get_api_key() -> str | None:
    return os.getenv("AZURE_OPENAI_API_KEY")


def _api_key_source(api_key: str | None) -> str:
    if not api_key:
        return ""

    for path in (PROJECT_ROOT_ENV, LEGACY_CIRA_ENV):
        if path.exists() and dotenv_values(path).get("AZURE_OPENAI_API_KEY") == api_key:
            return str(path)

    return "environment"


def get_api_key_status() -> dict[str, Any]:
    """Return safe, redacted diagnostics for the configured API key."""
    api_key = _get_api_key()
    if not api_key or api_key == "your_key_here":
        return {
            "loaded": False,
            "length": 0,
            "preview": "",
            "source": "",
        }

    preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    return {
        "loaded": True,
        "length": len(api_key),
        "preview": preview,
        "source": _api_key_source(api_key),
    }


def get_config_status() -> dict[str, Any]:
    """Return safe diagnostics for the active Azure OpenAI configuration."""
    key_status = get_api_key_status()
    return {
        **key_status,
        "endpoint": AZURE_OPENAI_ENDPOINT,
        "deployment": AZURE_OPENAI_DEPLOYMENT,
        "api_version": AZURE_OPENAI_API_VERSION,
    }


def _create_client() -> AzureOpenAI:
    api_key = _get_api_key()
    if not api_key or api_key == "your_key_here":
        raise ValueError(
            "AZURE_OPENAI_API_KEY is missing or not set. Copy .env.example to .env and add your key."
        )

    return AzureOpenAI(
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=api_key,
        timeout=90.0,
        max_retries=0,
    )


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from model output, including fenced JSON."""
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


def _retry_after_seconds(exc: APIStatusError, attempt: int) -> float:
    """Honour the server's Retry-After hint, falling back to capped exponential backoff."""
    header = exc.response.headers.get("Retry-After")
    if header:
        try:
            return min(float(header), MAX_RETRY_WAIT_SECONDS)
        except ValueError:
            pass

    return min(RETRY_BACKOFF_SECONDS * (2 ** attempt), MAX_RETRY_WAIT_SECONDS)


def _request_once(
    client: AzureOpenAI,
    messages: list[dict[str, str]],
    temperature: float,
    deployment: str,
) -> str:
    # The Azure GPT-5 sample omits temperature, and some deployments reject it.
    _ = temperature
    response = client.chat.completions.create(
        messages=messages,
        max_completion_tokens=AZURE_OPENAI_MAX_COMPLETION_TOKENS,
        model=deployment,
    )

    try:
        content = response.choices[0].message.content
    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Azure OpenAI response: {response}") from exc

    if not content:
        raise RuntimeError("Empty response from Azure OpenAI API.")
    return content.strip()


def call_azure_openai(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.35,
    model: str = AZURE_OPENAI_DEPLOYMENT,
) -> str:
    """Call Azure OpenAI chat completions and return text content.

    Retries transient errors (429 rate limits, 5xx) with backoff that respects the
    server's Retry-After hint, then falls back to AZURE_OPENAI_FALLBACK_DEPLOYMENTS
    if set.
    """
    deployments = [model, *[d for d in _fallback_deployments() if d != model]]
    last_error: Exception | None = None

    client = _create_client()
    for deployment_index, current_deployment in enumerate(deployments):
        for attempt in range(MAX_RETRIES + 1):
            try:
                return _request_once(client, messages, temperature, current_deployment)
            except APIStatusError as exc:
                status = exc.status_code
                detail = str(exc)[:500]
                last_error = RuntimeError(f"Azure OpenAI API error {status}: {detail}")
                if status not in RETRYABLE_STATUS or attempt == MAX_RETRIES:
                    break
                wait = _retry_after_seconds(exc, attempt)
                print(
                    f"[azure-openai] {current_deployment} returned {status}; "
                    f"retrying in {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})."
                )
                time.sleep(wait)
            except (APIConnectionError, APITimeoutError) as exc:
                last_error = RuntimeError(f"Azure OpenAI request failed: {exc}")
                if attempt == MAX_RETRIES:
                    break
                wait = min(RETRY_BACKOFF_SECONDS * (2 ** attempt), MAX_RETRY_WAIT_SECONDS)
                print(f"[azure-openai] request error; retrying in {wait:.1f}s.")
                time.sleep(wait)

        if deployment_index + 1 < len(deployments):
            print(f"[azure-openai] falling back to {deployments[deployment_index + 1]}.")

    raise last_error or RuntimeError("Azure OpenAI call failed with no response.")


def call_azure_openai_json(prompt: str, *, temperature: float = 0.2) -> dict[str, Any]:
    """Call Azure OpenAI with a single prompt and parse a JSON object response."""
    content = call_azure_openai(
        [{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return extract_json(content)
