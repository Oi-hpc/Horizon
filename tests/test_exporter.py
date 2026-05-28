from datetime import datetime, timezone

import pytest

from src.exporter import build_news_export
from src.models import ContentItem, ExportConfig, SourceType
from src.storage.manager import StorageManager


def _item() -> ContentItem:
    item = ContentItem(
        id="rss:test:1",
        source_type=SourceType.RSS,
        title="Original title",
        url="https://example.com/news/1",
        published_at=datetime(2026, 5, 27, 22, 30, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc),
        metadata={
            "feed_name": "Example Feed",
            "category": "finance",
            "ai_category": "finance",
            "title_zh": "中文标题",
            "detailed_summary_zh": "中文摘要",
            "sources": [{"title": "Reference", "url": "https://example.com/ref"}],
        },
    )
    item.ai_score = 8.2
    item.ai_reason = "Matches user interests."
    item.ai_summary = "Short AI summary."
    item.ai_tags = ["markets", "policy"]
    return item


def test_build_news_export_contains_content_workflow_fields():
    payload = build_news_export(
        items=[_item()],
        date="2026-05-28",
        total_fetched=10,
        total_analyzed=8,
        fetch_window_hours=24,
        languages=["zh"],
        profile="selected-news",
        workflow="selected_news",
        category_resolver=lambda item: "other",
    )

    assert payload["schema_version"] == "1.0"
    assert payload["timezone"] == "Asia/Shanghai"
    assert payload["config_profile"] == "selected-news"
    assert payload["stats"]["total_selected"] == 1
    assert payload["stats"]["category_counts"] == {"finance": 1}

    candidate = payload["candidates"][0]
    assert candidate["title"] == "Original title"
    assert candidate["title_zh"] == "中文标题"
    assert candidate["source"] == "Example Feed"
    assert candidate["published_at"] == "2026-05-28T06:30:00+08:00"
    assert candidate["summary"] == "中文摘要"
    assert candidate["scores"]["importance"] == 8.2
    assert candidate["selection_reason"] == "Matches user interests."
    assert candidate["compliance"]["sensitive_topics"] == ["finance"]
    assert candidate["provenance"]["related_urls"] == ["https://example.com/ref"]


def test_save_news_export_writes_dated_and_latest_files(tmp_path):
    storage = StorageManager(data_dir=str(tmp_path))
    payload = {"schema_version": "1.0", "candidates": []}

    dated, latest = storage.save_news_export(
        date="2026-05-28",
        payload=payload,
        profile="selected-news",
    )

    assert dated.name == "selected-news-2026-05-28.json"
    assert latest.name == "selected-news-latest.json"
    assert dated.read_text(encoding="utf-8") == latest.read_text(encoding="utf-8")


def test_export_profile_rejects_path_like_values():
    with pytest.raises(ValueError):
        ExportConfig(profile="../bad")
