"""Unit tests for ai_service parsing + provider resolution (no network)."""

import pytest

from app.services import ai_service
from app.services.ai_service import _extract_json


def test_direct_json():
    assert _extract_json('{"title": "Hi"}') == {"title": "Hi"}


def test_markdown_fenced_json():
    raw = '```json\n{"title": "Hi", "tags": ["a"]}\n```'
    assert _extract_json(raw) == {"title": "Hi", "tags": ["a"]}


def test_embedded_json_block():
    assert _extract_json('Here you go: {"title": "X"} thanks') == {"title": "X"}


def test_garbage_returns_none():
    assert _extract_json("not json at all") is None


def test_empty_returns_none():
    assert _extract_json("") is None


# --- provider resolution (resolve_backend) -------------------------------

async def _set_ollama(monkeypatch, available: bool):
    async def fake():
        return available
    monkeypatch.setattr(ai_service, "ollama_available", fake)


@pytest.mark.asyncio
async def test_auto_prefers_ollama(monkeypatch):
    await _set_ollama(monkeypatch, True)
    monkeypatch.setattr(ai_service, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "k")
    b = await ai_service.resolve_backend("auto")
    assert b is not None and b.provider == "ollama"


@pytest.mark.asyncio
async def test_auto_falls_back_to_claude(monkeypatch):
    await _set_ollama(monkeypatch, False)
    monkeypatch.setattr(ai_service, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "")
    b = await ai_service.resolve_backend("auto")
    assert b is not None and b.provider == "claude"
    assert b.model == ai_service.CLAUDE_MODEL


@pytest.mark.asyncio
async def test_auto_falls_back_to_openai(monkeypatch):
    await _set_ollama(monkeypatch, False)
    monkeypatch.setattr(ai_service, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "k")
    b = await ai_service.resolve_backend("auto")
    assert b is not None and b.provider == "openai"


@pytest.mark.asyncio
async def test_auto_none_when_nothing_available(monkeypatch):
    await _set_ollama(monkeypatch, False)
    monkeypatch.setattr(ai_service, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "")
    assert await ai_service.resolve_backend("auto") is None


@pytest.mark.asyncio
async def test_explicit_claude_requires_key(monkeypatch):
    await _set_ollama(monkeypatch, True)  # ollama up but explicitly want claude
    monkeypatch.setattr(ai_service, "ANTHROPIC_API_KEY", "")
    assert await ai_service.resolve_backend("claude") is None
    monkeypatch.setattr(ai_service, "ANTHROPIC_API_KEY", "k")
    b = await ai_service.resolve_backend("claude")
    assert b is not None and b.provider == "claude"


@pytest.mark.asyncio
async def test_explicit_ollama_model_override(monkeypatch):
    await _set_ollama(monkeypatch, True)
    b = await ai_service.resolve_backend("ollama", model="mistral:7b")
    assert b is not None and b.provider == "ollama" and b.model == "mistral:7b"
