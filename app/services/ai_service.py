"""AI client for generating YouTube metadata.

Primary backend is a local Ollama instance (free). When Ollama is unreachable,
the service falls back to a cloud provider if an API key is configured:

    OLLAMA  (local, free)         -> ANTHROPIC_API_KEY (Claude)  -> OPENAI_API_KEY

Selection is controlled per-call via ``provider`` ("auto" | "ollama" |
"claude" | "openai"). On any failure callers fall back to templated values.

Environment variables:
    OLLAMA_HOST        default http://localhost:11434
    OLLAMA_MODEL       default llama3.2:3b
    ANTHROPIC_API_KEY  enables Claude fallback
    CLAUDE_MODEL       default claude-haiku-4-5-20251001
    OPENAI_API_KEY     enables OpenAI fallback
    OPENAI_MODEL       default gpt-4o-mini
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
DEFAULT_TIMEOUT = 90.0

# Cloud fallbacks — only used when a key is present.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


@dataclass
class GeneratedMetadata:
    title: str
    description: str
    tags: list[str]


@dataclass
class Backend:
    provider: str  # ollama | claude | openai
    model: str


async def ollama_available() -> bool:
    """Return True if a local Ollama server answers on the configured host."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


# Backwards-compatible alias (older callers used ``is_available`` for Ollama).
async def is_available() -> bool:
    return await ollama_available()


async def list_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code != 200:
                return []
            data = r.json()
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


async def resolve_backend(provider: str = "auto",
                          model: str | None = None) -> Backend | None:
    """Pick an available metadata backend, honouring an explicit ``provider``.

    In "auto" mode the chosen Ollama ``model`` override is only applied to
    Ollama; cloud providers always use their own configured default model.
    Returns None when nothing usable is configured.
    """
    pref = (provider or "auto").lower()

    if pref == "ollama":
        return Backend("ollama", model or DEFAULT_MODEL) if await ollama_available() else None
    if pref == "claude":
        return Backend("claude", model or CLAUDE_MODEL) if ANTHROPIC_API_KEY else None
    if pref == "openai":
        return Backend("openai", model or OPENAI_MODEL) if OPENAI_API_KEY else None

    # auto: prefer free local Ollama, then Claude, then OpenAI.
    if await ollama_available():
        return Backend("ollama", model or DEFAULT_MODEL)
    if ANTHROPIC_API_KEY:
        return Backend("claude", CLAUDE_MODEL)
    if OPENAI_API_KEY:
        return Backend("openai", OPENAI_MODEL)
    return None


def _build_prompt(folder_name: str, part_number: int, total_parts: int,
                  duration_seconds: float, language: str) -> str:
    dur_min = max(1, round(duration_seconds / 60))
    lang_name = "Turkce" if language == "tr" else "English"
    return (
        f"You generate YouTube metadata. Respond with valid JSON only, no prose.\n"
        f"Language: {lang_name}.\n"
        f"Topic/folder: \"{folder_name}\".\n"
        f"This is part {part_number} of {total_parts} "
        f"(each ~{dur_min} minutes).\n"
        "Required JSON schema: "
        '{"title": string (max 80 chars), '
        '"description": string (3-6 short sentences, include a short '
        'call-to-action and a couple of relevant hashtags at the end), '
        '"tags": array of 8-15 short keyword strings}.\n'
        "Do not wrap the JSON in markdown. Output JSON only."
    )


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    # Try direct parse first
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Strip common markdown fences
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    # Fallback: find first {...} block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Provider backends — each returns raw model text (or None on failure)
# ---------------------------------------------------------------------------

async def _ollama_generate(prompt: str, model: str) -> str | None:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.7, "num_predict": 512},
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload)
            if r.status_code != 200:
                return None
            return r.json().get("response", "")
    except Exception:
        return None


async def _claude_generate(prompt: str, model: str) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.post("https://api.anthropic.com/v1/messages",
                                  json=payload, headers=headers)
            if r.status_code != 200:
                return None
            blocks = r.json().get("content") or []
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            return "\n".join(t for t in texts if t)
    except Exception:
        return None


async def _openai_generate(prompt: str, model: str) -> str | None:
    if not OPENAI_API_KEY:
        return None
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions",
                                  json=payload, headers=headers)
            if r.status_code != 200:
                return None
            choices = r.json().get("choices") or []
            if not choices:
                return None
            return (choices[0].get("message") or {}).get("content")
    except Exception:
        return None


def _finalize(parsed: dict | None) -> GeneratedMetadata | None:
    """Normalise a parsed JSON object into GeneratedMetadata (or None)."""
    if not parsed:
        return None

    title = (parsed.get("title") or "").strip()[:95]
    description = (parsed.get("description") or "").strip()[:4900]

    tags_raw = parsed.get("tags") or []
    tags: list[str] = []
    if isinstance(tags_raw, list):
        for t in tags_raw:
            if not t:
                continue
            s = str(t).strip().lstrip("#").strip()
            if s and s not in tags:
                tags.append(s)
            if len(tags) >= 15:
                break
    elif isinstance(tags_raw, str):
        for s in re.split(r"[,;]", tags_raw):
            s = s.strip().lstrip("#").strip()
            if s and s not in tags:
                tags.append(s)

    if not title:
        return None

    return GeneratedMetadata(title=title, description=description, tags=tags)


async def generate_metadata(
    folder_name: str,
    part_number: int,
    total_parts: int,
    duration_seconds: float = 300.0,
    language: str = "tr",
    model: str | None = None,
    provider: str = "auto",
) -> GeneratedMetadata | None:
    """Generate structured metadata via the first available backend.

    Returns None on any failure so callers can fall back to templates.
    """
    backend = await resolve_backend(provider, model)
    if not backend:
        return None

    prompt = _build_prompt(folder_name, part_number, total_parts,
                           duration_seconds, language)

    if backend.provider == "ollama":
        raw = await _ollama_generate(prompt, backend.model)
    elif backend.provider == "claude":
        raw = await _claude_generate(prompt, backend.model)
    elif backend.provider == "openai":
        raw = await _openai_generate(prompt, backend.model)
    else:
        raw = None

    return _finalize(_extract_json(raw or ""))
