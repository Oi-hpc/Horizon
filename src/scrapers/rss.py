"""RSS feed scraper implementation."""

import calendar
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import List
from email.utils import parsedate_to_datetime
import httpx
import feedparser

from .base import BaseScraper
from ..models import ContentItem, SourceType, RSSSourceConfig

logger = logging.getLogger(__name__)

RSS_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HorizonRSS/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


class RSSScraper(BaseScraper):
    """Scraper for RSS/Atom feeds."""

    def __init__(self, sources: List[RSSSourceConfig], http_client: httpx.AsyncClient):
        """Initialize RSS scraper.

        Args:
            sources: List of RSS feed configurations
            http_client: Shared async HTTP client
        """
        super().__init__({"sources": sources}, http_client)

    async def fetch(self, since: datetime) -> List[ContentItem]:
        """Fetch RSS feed items.

        Args:
            since: Only fetch items published after this time

        Returns:
            List[ContentItem]: Fetched content items
        """
        items = []
        sources = self.config["sources"]

        for source in sources:
            if not source.enabled:
                continue

            feed_items = await self._fetch_feed(source, since)
            items.extend(feed_items)

        return items

    async def _fetch_feed(
        self, source: RSSSourceConfig, since: datetime
    ) -> List[ContentItem]:
        """Fetch items from a single RSS feed.

        Args:
            source: RSS feed configuration
            since: Only fetch items after this time

        Returns:
            List[ContentItem]: Feed content items
        """
        items = []

        try:
            # Expand environment variables in URL (e.g. ${LWN_TOKEN})
            missing_env_vars = []
            feed_url = re.sub(
                r"\$\{(\w+)\}",
                lambda m: self._expand_env_var(m, missing_env_vars),
                str(source.url),
            )
            if missing_env_vars:
                logger.warning(
                    "Skipping RSS feed %s: missing environment variable(s): %s",
                    source.name,
                    ", ".join(missing_env_vars),
                )
                return []

            # Fetch feed content
            response = await self.client.get(
                feed_url,
                follow_redirects=True,
                headers=RSS_REQUEST_HEADERS,
            )
            response.raise_for_status()

            # Parse feed
            feed = feedparser.parse(response.text)

            for entry in feed.entries:
                # Parse published date
                published_at = self._parse_date(entry)
                if not published_at or published_at < since:
                    continue

                # Generate unique ID from feed URL and entry ID
                feed_id = str(source.url).split("//")[1].replace("/", "_")
                entry_id = entry.get("id", entry.get("link", ""))
                entry_hash = hashlib.sha256(str(entry_id).encode("utf-8")).hexdigest()[
                    :16
                ]

                # Extract content
                content = self._extract_content(entry)

                item = ContentItem(
                    id=self._generate_id("rss", feed_id, entry_hash),
                    source_type=SourceType.RSS,
                    title=entry.get("title", "Untitled"),
                    url=entry.get("link", str(source.url)),
                    content=content,
                    author=entry.get("author", source.name),
                    published_at=published_at,
                    metadata={
                        "feed_name": source.name,
                        "category": source.category,
                        "tags": [tag.term for tag in entry.get("tags", [])],
                    },
                )
                items.append(item)

        except httpx.HTTPError as e:
            logger.warning("Error fetching RSS feed %s: %s", source.name, e)
        except Exception as e:
            logger.warning("Error parsing RSS feed %s: %s", source.name, e)

        return items

    @staticmethod
    def _expand_env_var(match: re.Match[str], missing_env_vars: List[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        if value is None:
            missing_env_vars.append(name)
            return match.group(0)
        return value.strip()

    def _parse_date(self, entry: dict) -> datetime:
        """Parse publication date from feed entry.

        Args:
            entry: Feed entry data

        Returns:
            datetime: Parsed publication date or None
        """
        # Try different date fields
        for field in ["published", "updated", "created"]:
            if field in entry:
                try:
                    date_str = entry[field]
                    parsed = self._parse_date_string(str(date_str))
                    if parsed:
                        return parsed
                    if f"{field}_parsed" in entry and entry[f"{field}_parsed"]:
                        return datetime.fromtimestamp(
                            calendar.timegm(entry[f"{field}_parsed"]), tz=timezone.utc
                        )
                except Exception:
                    continue

        return None

    @staticmethod
    def _parse_date_string(date_str: str) -> datetime | None:
        date_str = date_str.strip()
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            pass

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(date_str, fmt)
                if fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                    parsed = parsed.replace(hour=23, minute=59, second=59)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        try:
            parsed = datetime.fromisoformat(date_str)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _extract_content(self, entry: dict) -> str:
        """Extract text content from feed entry.

        Args:
            entry: Feed entry data

        Returns:
            str: Extracted text content
        """
        # Try different content fields
        if "summary" in entry:
            return entry.summary
        if "description" in entry:
            return entry.description
        if "content" in entry and entry.content:
            # content is usually a list
            return entry.content[0].get("value", "")

        return ""
