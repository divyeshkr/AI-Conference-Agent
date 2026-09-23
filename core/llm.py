"""Provider-agnostic LLM access.

Supported providers: mock, openai, azure, gemini. The app is fully functional on
`mock`, which lets the team build and demo without any API credentials.
"""

from __future__ import annotations

import base64
import json
import random
import re
import time
from typing import Any

from .config import get_settings
from . import mockdata


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise LLMError(f"Model did not return JSON:\n{text[:500]}")
        return json.loads(match.group(0))


def _openai_client():
    from openai import AzureOpenAI, OpenAI

    s = get_settings()
    if s.provider == "azure":
        if not s.endpoint:
            raise LLMError("Azure provider selected but AZURE_OPENAI_ENDPOINT is not set.")
        return AzureOpenAI(
            api_key=s.api_key, azure_endpoint=s.endpoint, api_version=s.api_version
        )
    return OpenAI(api_key=s.api_key)


def _content_blocks(user: str, images: list[bytes] | None) -> Any:
    if not images:
        return user
    blocks: list[dict[str, Any]] = [{"type": "text", "text": user}]
    for img in images:
        b64 = base64.b64encode(img).decode()
        blocks.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        )
    return blocks


def _gemini_call(system: str, user: str, images: list[bytes] | None, json_mode: bool) -> str:
    from google import genai
    from google.genai import types

    s = get_settings()
    client = genai.Client(api_key=s.api_key)
    parts: list[Any] = [user]
    for img in images or []:
        parts.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    model = s.vision_model if images else s.text_model
    return client.models.generate_content(model=model, contents=parts, config=cfg).text


def _call_once(system: str, user: str, images: list[bytes] | None, json_mode: bool) -> str:
    s = get_settings()
    if s.provider == "gemini":
        return _gemini_call(system, user, images, json_mode)

    client = _openai_client()
    model = s.vision_model if images else s.text_model
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": _content_blocks(user, images)},
        ],
        response_format={"type": "json_object"} if json_mode else {"type": "text"},
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


# Free/shared model endpoints return 503 under load far more often than they fail
# outright. Retrying costs seconds; losing a card mid-demo costs the demo.
_TRANSIENT = ("503", "UNAVAILABLE", "overloaded", "high demand", "429",
              "RESOURCE_EXHAUSTED", "rate limit", "timeout", "502", "504")


def _is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}"
    return any(marker.lower() in text.lower() for marker in _TRANSIENT)


def _call(
    system: str,
    user: str,
    images: list[bytes] | None,
    json_mode: bool,
    attempts: int = 4,
) -> str:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return _call_once(system, user, images, json_mode)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if not _is_transient(exc) or attempt == attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 8) + random.random())
    raise last  # type: ignore[misc]


def complete_json(
    system: str,
    user: str,
    images: list[bytes] | None = None,
    mock_key: str = "generic",
) -> dict[str, Any]:
    """Structured call. Falls back to deterministic mock data when offline."""
    s = get_settings()
    if not s.is_live:
        return mockdata.mock_json(mock_key, user)
    try:
        return _extract_json(_call(system, user, images, json_mode=True))
    except Exception as exc:  # noqa: BLE001 - never let the demo hard-crash
        return {"_error": str(exc), **mockdata.mock_json(mock_key, user)}


def complete_text(system: str, user: str, images: list[bytes] | None = None) -> str:
    s = get_settings()
    if not s.is_live:
        return mockdata.mock_text(user)
    try:
        return _call(system, user, images, json_mode=False)
    except Exception as exc:  # noqa: BLE001
        return f"[LLM error: {exc}]\n\n{mockdata.mock_text(user)}"


def health_check() -> tuple[bool, str]:
    s = get_settings()
    if s.provider == "mock":
        return True, "Mock provider active — no API calls made."
    if not s.api_key:
        return False, "No API key set."
    try:
        _call("You are a health check.", "Reply with the single word OK.", None, False)
        return True, f"Connected to {s.provider} ({s.text_model})."
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
