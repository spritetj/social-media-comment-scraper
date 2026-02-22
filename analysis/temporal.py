"""
Temporal analysis — comment volume over time and peak patterns.
"""

from collections import Counter
from datetime import datetime


def _parse_date(date_str: str) -> datetime | None:
    """Try to parse a date string from various formats."""
    if not date_str:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%d %b %Y",
    ]

    # Clean common suffixes
    clean = date_str.strip()
    for suffix in [" (edited)", " ago"]:
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)]

    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt)
        except (ValueError, TypeError):
            continue

    # Try relative time parsing for YouTube-style dates
    # e.g., "2 days ago", "1 month ago"
    return None


def analyze_temporal(comments: list[dict]) -> dict:
    """Analyze comment timing patterns.

    Returns:
        {
            "by_date": [(date_str, count), ...],
            "by_hour": [(hour, count), ...],
            "by_day_of_week": [(day_name, count), ...],
            "peak_hour": int,
            "peak_day": str,
            "date_range": {"earliest": str, "latest": str},
            "parseable_count": int,
        }
    """
    if not comments:
        return {}

    parsed_dates = []
    for c in comments:
        dt = _parse_date(c.get("date", ""))
        if dt:
            parsed_dates.append(dt)

    if len(parsed_dates) < 5:
        return {
            "parseable_count": len(parsed_dates),
            "reason": "Not enough parseable dates for temporal analysis",
        }

    # By date (day granularity)
    date_counts = Counter(dt.strftime("%Y-%m-%d") for dt in parsed_dates)
    by_date = sorted(date_counts.items())

    # By hour of day
    hour_counts = Counter(dt.hour for dt in parsed_dates)
    by_hour = [(h, hour_counts.get(h, 0)) for h in range(24)]

    # By day of week
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_counts = Counter(dt.strftime("%A") for dt in parsed_dates)
    by_day_of_week = [(d, day_counts.get(d, 0)) for d in day_names]

    # Peak hour and day
    peak_hour = max(by_hour, key=lambda x: x[1])[0]
    peak_day = max(by_day_of_week, key=lambda x: x[1])[0]

    # Date range
    earliest = min(parsed_dates)
    latest = max(parsed_dates)

    return {
        "by_date": by_date,
        "by_hour": by_hour,
        "by_day_of_week": by_day_of_week,
        "peak_hour": peak_hour,
        "peak_day": peak_day,
        "date_range": {
            "earliest": earliest.strftime("%Y-%m-%d"),
            "latest": latest.strftime("%Y-%m-%d"),
        },
        "parseable_count": len(parsed_dates),
        "total_comments": len(comments),
    }
