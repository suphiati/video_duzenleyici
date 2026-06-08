"""Lightweight Ollama client for generating YouTube metadata locally (free).

The service talks to a local Ollama instance (http://localhost:11434) and
returns title, description and tags for a batch video. If Ollama is
unreachable, callers should fall back to templated values.
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


@dataclass
class GeneratedMetadata:
    title: str
    description: str
    tags: list[str]


async def is_available() -> bool:
    """Return True if a local Ollama server answers on the configured host."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


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


async def generate_metadata(
    folder_name: str,
    part_number: int,
    total_parts: int,
    duration_seconds: float = 300.0,
    language: str = "tr",
    model: str | None = None,
) -> GeneratedMetadata | None:
    """Call Ollama /api/generate and return structured metadata.

    Returns None on any failure so callers can fall back to templates.
    """
    model_name = model or DEFAULT_MODEL
    prompt = _build_prompt(folder_name, part_number, total_parts,
                           duration_seconds, language)
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.7,
            "num_predict": 512,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload)
            if r.status_code != 200:
                return None
            data = r.json()
            parsed = _extract_json(data.get("response", ""))
    except Exception:
        return None

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
