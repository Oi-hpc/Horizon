"""Preview categorized output from an existing Horizon Markdown summary.

This is a local smoke-test helper. It reconstructs lightweight ContentItem
objects from an already generated summary, runs only the new AI classification
step, then renders a categorized Markdown preview. It does not fetch, score,
deduplicate, or enrich news.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from src.ai.classifier import ContentClassifier
from src.ai.client import create_ai_client
from src.ai.summarizer import DailySummarizer
from src.models import ContentItem, SourceType
from src.storage.manager import StorageManager


ITEM_RE = re.compile(
    r'<a id="item-(?P<index>\d+)"></a>\s*'
    r'## \[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\) .*? (?P<score>[0-9.]+|\?)/10'
    r'(?P<body>.*?)(?=\n<a id="item-\d+"></a>|\Z)',
    re.S,
)
TAG_RE = re.compile(r"`#([^`]+)`")


def latest_summary() -> Path:
    summaries = sorted(
        Path("data/summaries").glob("horizon-*-zh.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not summaries:
        raise FileNotFoundError("No zh summaries found under data/summaries")
    return summaries[0]


def parse_items(markdown: str, limit: int | None = None) -> list[ContentItem]:
    items = []
    for match in ITEM_RE.finditer(markdown):
        if limit is not None and len(items) >= limit:
            break

        body = match.group("body").strip()
        lines = [line.rstrip() for line in body.splitlines()]
        summary_lines = []
        source_line = ""
        for line in lines:
            if line.startswith("**背景**") or line.startswith("<details>") or line.startswith("**社区讨论**") or line.startswith("**标签**"):
                break
            if " · " in line and not line.startswith("**") and not line.startswith("#"):
                source_line = line
                break
            if line:
                summary_lines.append(line)

        source_type, metadata = parse_source_line(source_line)
        tags = TAG_RE.findall(body)
        score_text = match.group("score")

        item = ContentItem(
            id=f"preview:{match.group('index')}",
            source_type=source_type,
            title=match.group("title"),
            url=match.group("url"),
            content="",
            author=metadata.get("author") or "preview",
            published_at=datetime.now(timezone.utc),
            metadata=metadata,
        )
        item.ai_score = None if score_text == "?" else float(score_text)
        item.ai_summary = " ".join(summary_lines).strip()
        item.ai_tags = tags
        items.append(item)
    return items


def parse_source_line(source_line: str) -> tuple[SourceType, dict]:
    if not source_line:
        return SourceType.RSS, {}

    parts = [part.strip() for part in source_line.split(" · ") if part.strip()]
    source = parts[0].lower() if parts else "rss"
    metadata: dict[str, str] = {"preview_source_line": source_line}

    if source == "github":
        return SourceType.GITHUB, metadata
    if source == "hackernews":
        return SourceType.HACKERNEWS, metadata
    if source == "reddit":
        for part in parts[1:]:
            if part.startswith("r/"):
                metadata["subreddit"] = part[2:]
                break
        return SourceType.REDDIT, metadata
    if source == "telegram":
        return SourceType.TELEGRAM, metadata
    if source == "twitter":
        return SourceType.TWITTER, metadata

    if len(parts) > 1:
        metadata["feed_name"] = parts[1]
    return SourceType.RSS, metadata


def infer_total_fetched(markdown: str, fallback: int) -> int:
    match = re.search(r"From\s+(\d+)\s+items", markdown)
    if match:
        return int(match.group(1))
    return fallback


def category_counts(items: Iterable[ContentItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        category = str(item.metadata.get("ai_category") or "unclassified")
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-ai", action="store_true", help="Render with rule fallback only")
    args = parser.parse_args()

    load_dotenv()
    input_path = args.input or latest_summary()
    markdown = input_path.read_text(encoding="utf-8")
    items = parse_items(markdown, limit=args.limit)
    if not items:
        raise RuntimeError(f"No items parsed from {input_path}")

    if not args.no_ai:
        config = StorageManager(data_dir="data").load_config()
        classifier = ContentClassifier(create_ai_client(config.ai))
        await classifier.classify_batch(items)

    date_match = re.search(r"horizon-(\d{4}-\d{2}-\d{2})-zh", input_path.name)
    date = date_match.group(1) if date_match else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_fetched = infer_total_fetched(markdown, fallback=len(items))
    rendered = await DailySummarizer().generate_summary(
        items,
        date=date,
        total_fetched=total_fetched,
        language="zh",
    )

    output_path = args.output or input_path.with_name(
        input_path.stem + "-classified-preview.md"
    )
    output_path.write_text(rendered, encoding="utf-8")

    print(f"input={input_path}")
    print(f"items={len(items)}")
    print(f"categories={category_counts(items)}")
    print(f"output={output_path}")


if __name__ == "__main__":
    asyncio.run(main())
