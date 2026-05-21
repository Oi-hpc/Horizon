"""Daily summary generation — pure programmatic rendering."""

import re
from typing import List, Dict, Tuple

from ..models import ContentItem


_CJK = r"[\u4e00-\u9fff\u3400-\u4dbf]"
_ASCII = r"[A-Za-z0-9]"


def _pangu(text: str) -> str:
    """Insert a space between CJK and ASCII letters/digits (Pangu spacing)."""
    text = re.sub(rf"({_CJK})({_ASCII})", r"\1 \2", text)
    text = re.sub(rf"({_ASCII})({_CJK})", r"\1 \2", text)
    return text


LABELS = {
    "en": {
        "header": "Horizon Daily",
        "toc": "Categories",
        "source": "Source",
        "background": "Background",
        "discussion": "Discussion",
        "references": "References",
        "tags": "Tags",
        "empty_body": (
            "No significant developments today. This might indicate:\n"
            "- A quiet day in your tracked sources\n"
            "- The AI score threshold is too high\n"
            "- Your information sources need expansion\n\n"
            "Consider:\n"
            "1. Lowering the `ai_score_threshold` in config.json\n"
            "2. Adding more diverse information sources\n"
            "3. Checking if the AI model is working correctly\n"
        ),
    },
    "zh": {
        "header": "Horizon 每日速递",
        "toc": "分类目录",
        "source": "来源",
        "background": "背景",
        "discussion": "社区讨论",
        "references": "参考链接",
        "tags": "标签",
        "empty_body": (
            "今日暂无重要动态，可能原因：\n"
            "- 今天关注的信息源较平静\n"
            "- AI 评分阈值设置过高\n"
            "- 信息源种类有待扩充\n\n"
            "建议：\n"
            "1. 在 config.json 中降低 `ai_score_threshold`\n"
            "2. 添加更多多样化的信息源\n"
            "3. 检查 AI 模型是否正常工作\n"
        ),
    },
}


CATEGORY_LABELS = {
    "ai": {"en": "AI / LLM", "zh": "AI / 大模型"},
    "semiconductors": {"en": "Semiconductors", "zh": "半导体"},
    "china": {"en": "China", "zh": "中国新闻"},
    "world": {"en": "World / Politics", "zh": "国际政治"},
    "finance": {"en": "Finance / Markets", "zh": "财经 / 市场"},
    "github": {"en": "GitHub / Open Source", "zh": "GitHub / 开源"},
    "software": {"en": "Software Engineering", "zh": "软件工程"},
    "other": {"en": "Other", "zh": "其他"},
}

CATEGORY_ORDER = [
    "ai",
    "semiconductors",
    "china",
    "world",
    "finance",
    "github",
    "software",
    "other",
]


class DailySummarizer:
    """Generates daily Markdown summaries from pre-analyzed content items."""

    def __init__(self):
        pass

    async def generate_summary(
        self,
        items: List[ContentItem],
        date: str,
        total_fetched: int,
        language: str = "en",
    ) -> str:
        """Generate daily summary in Markdown format.

        Items are rendered in score-descending order (already sorted by orchestrator).

        Args:
            items: High-scoring content items (already enriched)
            date: Date string (YYYY-MM-DD)
            total_fetched: Total number of items fetched before filtering
            language: Output language, either "en" or "zh"

        Returns:
            str: Markdown formatted summary
        """
        labels = LABELS.get(language, LABELS["en"])

        if not items:
            return self._generate_empty_summary(date, total_fetched, labels)

        header = (
            f"# {labels['header']} - {date}\n\n"
            f"> From {total_fetched} items, {len(items)} important content pieces were selected\n\n"
            "---\n\n"
        )

        grouped_items = self._group_items(items)

        # TOC
        toc_entries = []
        index = 1
        for category, category_items in grouped_items:
            label = self._category_label(category, language)
            toc_entries.append(f"**{label} ({len(category_items)})**")
            toc_entries.append("")
            for item in category_items:
                _t = item.metadata.get(f"title_{language}") or item.title
                t = str(_t).replace("[", "(").replace("]", ")")
                if language == "zh":
                    t = _pangu(t)
                score = item.ai_score or "?"
                toc_entries.append(f"{index}. [{t}](#item-{index}) \u2b50\ufe0f {score}/10")
                toc_entries.append("")
                index += 1
            toc_entries.append("")
        toc = f"## {labels['toc']}\n\n" + "\n".join(toc_entries).rstrip() + "\n\n---\n\n"

        parts = []
        index = 1
        for category, category_items in grouped_items:
            label = self._category_label(category, language)
            parts.append(f"## {label}\n\n")
            for item in category_items:
                parts.append(self._format_item(item, labels, language, index, heading_level=3))
                index += 1

        return header + toc + "".join(parts)

    def generate_webhook_overview(
        self,
        items: List[ContentItem],
        date: str,
        total_fetched: int,
        language: str = "en",
    ) -> str:
        """Generate a compact overview for multi-message webhook delivery."""
        labels = LABELS.get(language, LABELS["en"])
        if not items:
            return self._generate_empty_summary(date, total_fetched, labels)

        if language == "zh":
            header = (
                f"# {labels['header']} - {date}\n\n"
                f"> 从 {total_fetched} 条内容中筛选出 {len(items)} 条重要资讯。\n\n"
                "下面会按新闻逐条发送详情，你可以只看感兴趣的标题。\n\n"
            )
        else:
            header = (
                f"# {labels['header']} - {date}\n\n"
                f"> Selected {len(items)} important items from {total_fetched} fetched items.\n\n"
                "Details will be sent item by item so you can read only the topics you care about.\n\n"
            )

        entries = []
        index = 1
        for category, category_items in self._group_items(items):
            label = self._category_label(category, language)
            entries.append(f"## {label} ({len(category_items)})")
            entries.append("")
            for item in category_items:
                title = str(item.metadata.get(f"title_{language}") or item.title).replace("[", "(").replace("]", ")")
                if language == "zh":
                    title = _pangu(title)
                score = item.ai_score or "?"
                entries.append(f"{index}. [{title}]({item.url}) \u2b50\ufe0f {score}/10")
                entries.append("")
                index += 1
            entries.append("")

        return header + "\n".join(entries).rstrip()

    def generate_webhook_item(
        self,
        item: ContentItem,
        language: str,
        index: int,
        total: int,
    ) -> str:
        """Generate one item message for multi-message webhook delivery."""
        labels = LABELS.get(language, LABELS["en"])
        prefix = f"第 {index}/{total} 条\n\n" if language == "zh" else f"Item {index}/{total}\n\n"
        return prefix + self._format_item(item, labels, language, index).rstrip("-\n ")

    def _format_item(
        self,
        item: ContentItem,
        labels: dict,
        language: str,
        index: int,
        heading_level: int = 2,
    ) -> str:
        """Format a single ContentItem into Markdown."""
        _title = item.metadata.get(f"title_{language}") or item.title
        title = str(_title).replace("[", "(").replace("]", ")")
        url = str(item.url)
        score = item.ai_score or "?"
        meta = item.metadata

        summary = (
            meta.get(f"detailed_summary_{language}")
            or meta.get("detailed_summary")
            or item.ai_summary
            or ""
        )
        background = meta.get(f"background_{language}") or meta.get("background") or ""
        discussion = (
            meta.get(f"community_discussion_{language}")
            or meta.get("community_discussion")
            or ""
        )

        if language == "zh":
            title = _pangu(title)
            summary = _pangu(summary)
            background = _pangu(background)
            discussion = _pangu(discussion)

        # Source line with parts joined by " · ", link appended at end
        source_type = item.source_type.value
        source_parts = [source_type]
        if meta.get("subreddit"):
            source_parts.append(f"r/{meta['subreddit']}")
        if meta.get("feed_name"):
            source_parts.append(meta["feed_name"])
        else:
            source_parts.append(item.author or "unknown")
        if item.published_at:
            day = item.published_at.strftime("%d").lstrip("0")
            source_parts.append(item.published_at.strftime(f"%b {day}, %H:%M"))
        source_line = " \u00b7 ".join(source_parts)  # ·

        discussion_url = meta.get("discussion_url")
        if discussion_url:
            discussion_url = str(discussion_url)
            if discussion_url != url:
                source_line += f' · [{labels["discussion"]}]({discussion_url})'

        heading = "#" * heading_level
        lines = [
            f'<a id="item-{index}"></a>',
            f"{heading} [{title}]({url}) \u2b50\ufe0f {score}/10",  # ⭐️
            "",
            summary,
            "",
            source_line,
        ]

        if background:
            lines.append("")
            lines.append(f"**{labels['background']}**: {background}")

        sources = meta.get("sources") or []
        if sources:
            items_html = "".join(f'<li><a href="{s["url"]}">{s["title"]}</a></li>\n' for s in sources)
            lines += [
                "",
                f'<details><summary>{labels["references"]}</summary>\n<ul>\n{items_html}\n</ul>\n</details>',
            ]

        if discussion:
            lines.append("")
            lines.append(f"**{labels['discussion']}**: {discussion}")

        if item.ai_tags:
            tags_str = ", ".join([f"`#{t}`" for t in item.ai_tags])
            lines.append("")
            lines.append(f"**{labels['tags']}**: {tags_str}")

        lines.append("")
        lines.append("---")

        return "\n".join(lines) + "\n\n"

    def _group_items(self, items: List[ContentItem]) -> List[Tuple[str, List[ContentItem]]]:
        grouped: Dict[str, List[ContentItem]] = {key: [] for key in CATEGORY_ORDER}
        for item in items:
            grouped[self._category_key(item)].append(item)

        return [
            (key, sorted(grouped[key], key=lambda item: item.ai_score or 0, reverse=True))
            for key in CATEGORY_ORDER
            if grouped[key]
        ]

    def _category_label(self, category: str, language: str) -> str:
        labels = CATEGORY_LABELS.get(category, CATEGORY_LABELS["other"])
        return labels.get(language, labels["en"])

    def _category_key(self, item: ContentItem) -> str:
        meta = item.metadata or {}
        ai_category = str(meta.get("ai_category") or "").lower()
        if ai_category in CATEGORY_LABELS:
            return ai_category

        source_type = item.source_type.value
        source_category = str(meta.get("category") or "").lower()
        subreddit = str(meta.get("subreddit") or "").lower()
        feed_name = str(meta.get("feed_name") or "").lower()
        tags = " ".join(str(tag).lower() for tag in (item.ai_tags or []))
        haystack = " ".join(
            [
                item.title.lower(),
                item.ai_summary.lower() if item.ai_summary else "",
                source_type,
                source_category,
                subreddit,
                feed_name,
                tags,
            ]
        )

        explicit_categories = {
            "world-news": "world",
            "china-news": "china",
            "china-geopolitics": "china",
            "business-news": "finance",
            "markets": "finance",
            "semiconductors": "semiconductors",
            "github-trending": "github",
            "linux-kernel": "software",
            "ai-tools": "ai",
        }
        if source_category in explicit_categories:
            return explicit_categories[source_category]

        if source_type == "github":
            return "github"

        if subreddit in {
            "machinelearning",
            "localllama",
            "stablediffusion",
            "artificial",
            "openai",
            "chatgpt",
            "chatgptcoding",
        }:
            return "ai"
        if subreddit in {"commandline", "sideproject", "technology"}:
            return "software"

        keyword_categories = [
            ("semiconductors", ("semiconductor", "chip", "foundry", "wafer", "hbm", "tsmc", "asml", "intel", "nvidia")),
            ("china", ("china", "chinese", "beijing", "taiwan", "hong kong", "中国", "北京", "台湾", "香港")),
            ("world", ("politics", "geopolitics", "election", "war", "ukraine", "russia", "israel", "gaza", "tariff")),
            ("finance", ("finance", "market", "stock", "earnings", "inflation", "fed", "rate", "cnbc", "marketwatch", "财经", "股市")),
            ("ai", ("ai", "llm", "model", "inference", "machine learning", "openai", "anthropic", "deepseek", "qwen", "agent")),
            ("github", ("github", "open source", "repository", "release", "repo")),
            ("software", ("software", "python", "rust", "linux", "compiler", "database", "developer", "programming", "systems")),
        ]
        for category, keywords in keyword_categories:
            if any(keyword in haystack for keyword in keywords):
                return category

        if source_type == "hackernews":
            return "software"
        return "other"

    def _generate_empty_summary(self, date: str, total_fetched: int, labels: dict) -> str:
        """Generate summary when no high-scoring items were found."""
        return (
            f"# {labels['header']} - {date}\n\n"
            f"> Analyzed {total_fetched} items, but none met the importance threshold.\n\n"
            + labels["empty_body"]
        )
