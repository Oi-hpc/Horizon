from datetime import datetime, timezone

from src.time_utils import to_report_time


def test_to_report_time_converts_utc_to_china_time():
    moment = datetime(2026, 5, 23, 21, 0, tzinfo=timezone.utc)

    assert to_report_time(moment).strftime("%Y-%m-%d %H:%M %z") == "2026-05-24 05:00 +0800"


def test_to_report_time_treats_naive_datetime_as_utc():
    moment = datetime(2026, 5, 23, 21, 0)

    assert to_report_time(moment).strftime("%Y-%m-%d %H:%M %z") == "2026-05-24 05:00 +0800"
