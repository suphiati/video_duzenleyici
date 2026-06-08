"""Unit tests for batch_service._build_metadata (template + AI-merge paths).

The AI path is exercised by monkeypatching ai_service.generate_metadata, so no
Ollama server is required.
"""

import pytest

from app.services import batch_service, ai_service


@pytest.mark.asyncio
async def test_template_path_when_ai_disabled():
    title, desc, tags = await batch_service._build_metadata(
        folder_name="Tatil", part_number=2, total_parts=5,
        target_duration=300,
        youtube_settings={
            "title_template": "{folder_name} - Bolum {part_number}",
            "description": "Aciklama",
            "tags": ["tag1", "tag2"],
        },
        ai_settings=None,
    )
    assert title == "Tatil - Bolum 2"
    assert desc == "Aciklama"
    assert tags == ["tag1", "tag2"]


@pytest.mark.asyncio
async def test_default_template_when_no_settings():
    title, desc, tags = await batch_service._build_metadata(
        folder_name="X", part_number=1, total_parts=1, target_duration=60,
        youtube_settings={}, ai_settings={"enabled": False},
    )
    assert title == "X - Bolum 1"
    assert desc == ""
    assert tags == []


@pytest.mark.asyncio
async def test_ai_tags_merge_and_dedup(monkeypatch):
    async def fake_generate(**kwargs):
        return ai_service.GeneratedMetadata(
            title="AI Title", description="AI desc", tags=["x", "y", "tag1"]
        )
    monkeypatch.setattr(ai_service, "generate_metadata", fake_generate)

    title, desc, tags = await batch_service._build_metadata(
        folder_name="F", part_number=1, total_parts=1, target_duration=60,
        youtube_settings={"description": "base", "tags": ["tag1", "tag2"]},
        ai_settings={"enabled": True, "append_default_description": True},
    )
    assert title == "AI Title"
    assert "base" in desc and "AI desc" in desc
    assert tags.count("tag1") == 1          # case-insensitive dedup
    assert {"tag1", "tag2", "x", "y"}.issubset(set(tags))
