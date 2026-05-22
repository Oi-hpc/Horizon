"""AI-powered topic classification for selected news items."""

from typing import Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from .client import AIClient
from .prompts import NEWS_CLASSIFICATION_SYSTEM, NEWS_CLASSIFICATION_USER
from .utils import parse_json_response
from ..models import ContentItem


ALLOWED_CATEGORIES = {
    "ai",
    "semiconductors",
    "policy",
    "shenzhen",
    "livelihood",
    "real_estate",
    "china",
    "world",
    "finance",
    "github",
    "software",
    "other",
}


class ContentClassifier:
    """Classifies high-scoring news items into stable briefing categories."""

    def __init__(self, ai_client: AIClient, batch_size: int = 25):
        self.client = ai_client
        self.batch_size = max(batch_size, 1)

    async def classify_batch(self, items: List[ContentItem]) -> None:
        """Classify selected items in-place via ``metadata['ai_category']``."""
        for start in range(0, len(items), self.batch_size):
            batch = items[start : start + self.batch_size]
            try:
                categories = await self._classify_chunk(batch)
            except Exception as exc:
                print(f"Warning: item classification failed: {exc}")
                continue

            for index, category in categories.items():
                if 0 <= index < len(batch) and category in ALLOWED_CATEGORIES:
                    batch[index].metadata["ai_category"] = category

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=10),
    )
    async def _classify_chunk(self, items: List[ContentItem]) -> Dict[int, str]:
        rendered_items = "\n\n".join(
            self._render_item(item, index)
            for index, item in enumerate(items, start=1)
        )
        response = await self.client.complete(
            system=NEWS_CLASSIFICATION_SYSTEM,
            user=NEWS_CLASSIFICATION_USER.format(items=rendered_items),
        )
        parsed = parse_json_response(response)
        if parsed is None:
            raise ValueError("Could not parse classification JSON")
        return self._extract_categories(parsed)

    def _extract_categories(self, parsed: dict) -> Dict[int, str]:
        results: Dict[int, str] = {}
        entries = parsed.get("items", [])
        if isinstance(entries, dict):
            entries = [
                {"index": key, "category": value}
                for key, value in entries.items()
            ]

        if not isinstance(entries, list):
            return results

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            index = self._parse_index(entry.get("index"))
            category = str(entry.get("category", "")).strip().lower()
            if index is not None and category in ALLOWED_CATEGORIES:
                results[index - 1] = category
        return results

    @staticmethod
    def _parse_index(value: object) -> Optional[int]:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        return index if index > 0 else None

    def _render_item(self, item: ContentItem, index: int) -> str:
        meta = item.metadata or {}
        summary = (
            meta.get("detailed_summary_zh")
            or meta.get("detailed_summary_en")
            or meta.get("detailed_summary")
            or item.ai_summary
            or ""
        )
        background = (
            meta.get("background_zh")
            or meta.get("background_en")
            or meta.get("background")
            or ""
        )
        source_bits = [item.source_type.value]
        for key in ("feed_name", "category", "subreddit", "repo", "flair"):
            if meta.get(key):
                source_bits.append(f"{key}={meta[key]}")

        return "\n".join(
            [
                f"Index: {index}",
                f"Title: {item.title}",
                f"Summary: {str(summary)[:600]}",
                f"Background: {str(background)[:400]}",
                f"Tags: {', '.join(item.ai_tags or [])}",
                f"Source: {'; '.join(source_bits)}",
            ]
        )
