"""Structured exports for downstream workflows."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Callable, Iterable

from .models import ContentItem
from .time_utils import REPORT_TIMEZONE, to_report_time


REPORT_TIMEZONE_NAME = "Asia/Shanghai"


def build_news_export(
    *,
    items: list[ContentItem],
    date: str,
    total_fetched: int,
    total_analyzed: int,
    fetch_window_hours: int,
    languages: Iterable[str],
    profile: str,
    workflow: str,
    category_resolver: Callable[[ContentItem], str],
) -> dict:
    """Build a stable JSON payload for selected news/content candidates."""
    language_list = list(languages) or ["en"]
    candidates = [
        _item_to_candidate(item, language_list, category_resolver)
        for item in items
    ]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(REPORT_TIMEZONE).isoformat(timespec="seconds"),
        "timezone": REPORT_TIMEZONE_NAME,
        "date": date,
        "workflow": workflow,
        "config_profile": profile,
        "fetch_window_hours": fetch_window_hours,
        "languages": language_list,
        "stats": {
            "total_fetched": total_fetched,
            "total_analyzed": total_analyzed,
            "total_selected": len(candidates),
            "source_counts": dict(Counter(c["source_type"] for c in candidates)),
            "category_counts": dict(Counter(c["category"] for c in candidates)),
        },
        "candidates": candidates,
    }


def _item_to_candidate(
    item: ContentItem,
    languages: list[str],
    category_resolver: Callable[[ContentItem], str],
) -> dict:
    meta = item.metadata or {}
    category = str(meta.get("ai_category") or category_resolver(item) or "other")
    source_category = meta.get("category")
    summaries = _language_map(meta, "detailed_summary", languages)
    titles = _language_map(meta, "title", languages)
    primary_language = languages[0] if languages else "en"
    primary_summary = (
        summaries.get(primary_language)
        or summaries.get("zh")
        or summaries.get("en")
        or meta.get("detailed_summary")
        or item.ai_summary
        or ""
    )

    source = _source_label(item)
    related_sources = [
        {"title": str(src.get("title", "")), "url": str(src.get("url", ""))}
        for src in (meta.get("sources") or [])
        if isinstance(src, dict) and src.get("url")
    ]

    return {
        "id": item.id,
        "title": item.title,
        "title_zh": titles.get("zh"),
        "title_en": titles.get("en"),
        "titles": titles,
        "url": str(item.url),
        "source": source,
        "source_type": item.source_type.value,
        "source_category": source_category,
        "published_at": _iso_report_time(item.published_at),
        "fetched_at": _iso_report_time(item.fetched_at),
        "category": category,
        "subcategories": _subcategories(category, source_category),
        "tags": list(item.ai_tags or []),
        "summary": primary_summary,
        "summaries": summaries,
        "key_points": _as_string_list(meta.get("key_points")),
        "scores": {
            "importance": _float_or_none(item.ai_score),
            "interest_match": _float_or_none(meta.get("interest_match")),
            "content_potential": _float_or_none(meta.get("content_potential")),
            "visual_potential": _float_or_none(meta.get("visual_potential")),
            "timeliness": _float_or_none(meta.get("timeliness")),
            "risk": _float_or_none(meta.get("risk")),
            "overall": _float_or_none(item.ai_score),
        },
        "selection_reason": item.ai_reason or "",
        "content_angle": meta.get("content_angle"),
        "audience_value": meta.get("audience_value"),
        "why_now": meta.get("why_now"),
        "visual_brief": {
            "prompt_hint": meta.get("visual_prompt_hint"),
            "style": meta.get("visual_style"),
            "avoid": _visual_avoid_list(category),
        },
        "platform_fit": _platform_fit(meta),
        "compliance": {
            "sensitive_topics": _sensitive_topics(category),
            "needs_fact_check": True,
            "avoid_claims": _avoid_claims(category),
        },
        "provenance": {
            "dedup_group": meta.get("dedup_group") or _dedup_group(item),
            "merged_sources": meta.get("merged_sources", []),
            "related_urls": [src["url"] for src in related_sources],
            "related_sources": related_sources,
        },
        "horizon_analysis": {
            "score": _float_or_none(item.ai_score),
            "reason": item.ai_reason,
            "summary": item.ai_summary,
            "tags": list(item.ai_tags or []),
        },
    }


def _language_map(meta: dict, field: str, languages: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for lang in dict.fromkeys([*languages, "zh", "en"]):
        value = meta.get(f"{field}_{lang}")
        if value:
            values[lang] = str(value)
    return values


def _source_label(item: ContentItem) -> str:
    meta = item.metadata or {}
    if meta.get("feed_name"):
        return str(meta["feed_name"])
    if meta.get("subreddit"):
        return f"r/{meta['subreddit']}"
    if meta.get("channel"):
        return f"@{meta['channel']}"
    if meta.get("repo"):
        return str(meta["repo"])
    if meta.get("watchlist"):
        return str(meta["watchlist"])
    return item.author or item.source_type.value


def _iso_report_time(moment) -> str | None:
    if not moment:
        return None
    return to_report_time(moment).isoformat(timespec="seconds")


def _subcategories(category: str, source_category) -> list[str]:
    values = [category]
    if source_category and source_category not in values:
        values.append(str(source_category))
    return values


def _as_string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if value:
        return [str(value)]
    return []


def _float_or_none(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _platform_fit(meta: dict) -> dict[str, float | None]:
    raw = meta.get("platform_fit")
    defaults: dict[str, float | None] = {
        "wechat": None,
        "xiaohongshu": None,
        "weibo": None,
        "zhihu": None,
    }
    if not isinstance(raw, dict):
        return defaults
    for key in defaults:
        defaults[key] = _float_or_none(raw.get(key))
    return defaults


def _sensitive_topics(category: str) -> list[str]:
    sensitive = {
        "finance",
        "policy",
        "china",
        "world",
        "livelihood",
        "real_estate",
        "shenzhen",
    }
    return [category] if category in sensitive else []


def _avoid_claims(category: str) -> list[str]:
    common = ["Do not invent facts, figures, quotes, or source attributions."]
    if category == "finance":
        return common + [
            "Do not provide investment advice or price predictions.",
            "Do not imply guaranteed returns.",
        ]
    if category in {"policy", "china", "world", "shenzhen"}:
        return common + [
            "Do not overstate policy intent beyond the source material.",
            "Avoid inflammatory framing and unverified accusations.",
        ]
    if category == "real_estate":
        return common + [
            "Do not imply a guaranteed property-market direction.",
            "Avoid individual purchase recommendations.",
        ]
    return common


def _visual_avoid_list(category: str) -> list[str]:
    avoid = ["misleading charts", "fake screenshots", "fabricated logos"]
    if category in {"policy", "china", "world"}:
        avoid.extend(["political leader likenesses", "national flags as propaganda"])
    if category == "finance":
        avoid.extend(["fake stock prices", "guaranteed profit imagery"])
    return avoid


def _dedup_group(item: ContentItem) -> str:
    return str(item.url).split("#", 1)[0].rstrip("/")
