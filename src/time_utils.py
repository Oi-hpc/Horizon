"""Shared time helpers for reporting and display."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


try:
    REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")
except Exception:
    REPORT_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def report_date() -> str:
    """Return the report date in the reader-facing timezone."""
    return datetime.now(REPORT_TIMEZONE).strftime("%Y-%m-%d")


def to_report_time(moment: datetime) -> datetime:
    """Convert a source timestamp to the reader-facing timezone."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(REPORT_TIMEZONE)
