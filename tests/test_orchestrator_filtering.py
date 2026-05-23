from datetime import datetime, timezone

from src.models import (
    AIConfig,
    AIProvider,
    Config,
    ContentItem,
    FilteringConfig,
    SourceType,
    SourcesConfig,
)
from src.orchestrator import HorizonOrchestrator, infer_filter_category


def _item(item_id: str, score: float, category: str) -> ContentItem:
    item = ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=f"{category} item {item_id}",
        url=f"https://example.com/{item_id.replace(':', '-')}",
        published_at=datetime(2026, 5, 23, 8, 0, tzinfo=timezone.utc),
        metadata={"category": category},
    )
    item.ai_score = score
    item.ai_summary = f"Summary for {item_id}"
    return item


def test_select_important_items_applies_category_thresholds_and_caps():
    config = Config(
        ai=AIConfig(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            api_key_env="OPENAI_API_KEY",
        ),
        sources=SourcesConfig(),
        filtering=FilteringConfig(
            ai_score_threshold=7.0,
            time_window_hours=24,
            category_score_thresholds={
                "ai": 7.5,
                "semiconductors": 7.5,
                "shenzhen": 6.0,
            },
            category_limits={
                "ai": 12,
                "semiconductors": 6,
            },
        ),
    )
    orchestrator = HorizonOrchestrator(config, storage=object())

    items = []
    items.extend(_item(f"rss:ai-{idx}", 8.0, "ai-tools") for idx in range(15))
    items.extend(
        _item(f"rss:semi-{idx}", 8.0, "semiconductors") for idx in range(8)
    )
    items.append(_item("rss:shenzhen-low", 6.2, "shenzhen"))
    items.append(_item("rss:china-low", 6.5, "china-news"))
    items.append(_item("rss:finance-global", 7.1, "finance"))

    selected = orchestrator._select_important_items(items)
    selected_ids = {item.id for item in selected}

    assert sum(1 for item in selected if infer_filter_category(item) == "ai") == 12
    assert (
        sum(1 for item in selected if infer_filter_category(item) == "semiconductors")
        == 6
    )
    assert "rss:shenzhen-low" in selected_ids
    assert "rss:china-low" not in selected_ids
    assert "rss:finance-global" in selected_ids


def test_infer_filter_category_supports_chinese_ai_and_chip_keywords():
    ai_item = _item("rss:zh-ai", 8.0, "")
    ai_item.title = "国产大模型推理成本继续下降"
    semi_item = _item("rss:zh-chip", 8.0, "")
    semi_item.title = "先进制程芯片产能扩张"
    finance_chip_item = _item("rss:finance-chip", 8.0, "finance")
    finance_chip_item.title = "HBM supply constraints reshape memory pricing"

    assert infer_filter_category(ai_item) == "ai"
    assert infer_filter_category(semi_item) == "semiconductors"
    assert infer_filter_category(finance_chip_item) == "semiconductors"
