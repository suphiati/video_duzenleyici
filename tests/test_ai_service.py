"""Unit tests for ai_service._extract_json (pure parsing, no Ollama)."""

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
