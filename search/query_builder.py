"""
Query builder — expand user topic into Google dork queries per platform.

Supports full Google operators: site:, intext:, -inurl:, after:, before:, etc.
Generates diverse query variations to maximize unique URL discovery.
"""

from datetime import datetime, timedelta


# Platform-specific Google dork patterns
# Each platform has many patterns with different modifiers to maximize coverage.
_PLATFORM_CONFIG = {
    "youtube": {
        "site": "youtube.com",
        "patterns": [
            'site:youtube.com/watch "{topic}"',
            'site:youtube.com "{topic}" review',
            'site:youtube.com "{topic}" discussion',
            'site:youtube.com "{topic}" experience',
            'site:youtube.com "{topic}" opinion',
            'site:youtube.com "{topic}" honest',
            'site:youtube.com "{topic}" problems',
            'site:youtube.com "{topic}" worth it',
            'site:youtube.com/shorts "{topic}"',
            'site:youtube.com "{topic}" comparison',
        ],
    },
    "tiktok": {
        "site": "tiktok.com",
        "patterns": [
            'site:tiktok.com "{topic}"',
            'site:tiktok.com "{topic}" review',
            'site:tiktok.com/@* "{topic}"',
            'site:tiktok.com "{topic}" honest',
            'site:tiktok.com "{topic}" experience',
            'site:tiktok.com "{topic}" viral',
            'site:tiktok.com "{topic}" worth',
            'site:tiktok.com "{topic}" try',
            'site:tiktok.com "{topic}" unboxing',
            'site:tiktok.com "{topic}" opinion',
        ],
    },
    "facebook": {
        "site": "facebook.com",
        "patterns": [
            'site:facebook.com "{topic}"',
            'site:facebook.com/*/posts "{topic}"',
            'site:facebook.com "{topic}" review',
            'site:facebook.com "{topic}" group',
            'site:facebook.com "{topic}" experience',
            'site:facebook.com "{topic}" recommend',
            'site:facebook.com "{topic}" opinion',
            'site:facebook.com "{topic}" problem',
            'site:facebook.com "{topic}" discussion',
            'site:facebook.com "{topic}" worth',
        ],
    },
    "instagram": {
        "site": "instagram.com",
        "patterns": [
            'site:instagram.com/p/ "{topic}"',
            'site:instagram.com/reel/ "{topic}"',
            'site:instagram.com "{topic}"',
            'site:instagram.com "{topic}" review',
            'site:instagram.com "{topic}" honest',
            'site:instagram.com "{topic}" experience',
            'site:instagram.com "{topic}" try',
            'site:instagram.com "{topic}" unboxing',
        ],
    },
}


def build_queries(
    topic: str,
    platforms: list[str] | None = None,
    date_range: str = "any",
    max_queries_per_platform: int = 10,
) -> dict[str, list[str]]:
    """Expand a topic into Google dork queries per platform.

    Args:
        topic: User's search topic (e.g., "Tesla Model 3")
        platforms: List of platforms to search (default: all)
        date_range: "week", "month", "year", or "any"
        max_queries_per_platform: Max queries per platform

    Returns:
        {"youtube": [query1, query2, ...], "tiktok": [...], ...}
    """
    if platforms is None:
        platforms = list(_PLATFORM_CONFIG.keys())

    date_filter = _build_date_filter(date_range)

    queries = {}
    for platform in platforms:
        config = _PLATFORM_CONFIG.get(platform)
        if not config:
            continue

        platform_queries = []
        for pattern in config["patterns"][:max_queries_per_platform]:
            query = pattern.format(topic=topic)
            if date_filter:
                query = f"{query} {date_filter}"
            platform_queries.append(query)

        queries[platform] = platform_queries

    return queries


def _build_date_filter(date_range: str) -> str:
    """Build Google date filter string."""
    if date_range == "any":
        return ""

    now = datetime.now()
    if date_range == "week":
        after = now - timedelta(days=7)
    elif date_range == "month":
        after = now - timedelta(days=30)
    elif date_range == "year":
        after = now - timedelta(days=365)
    else:
        return ""

    return f"after:{after.strftime('%Y-%m-%d')}"


def expand_topic(topic: str) -> list[str]:
    """Generate query variations from a topic."""
    variations = [topic]
    modifiers = ["review", "experience", "opinion", "thoughts on", "problem with"]
    for mod in modifiers[:3]:
        variations.append(f"{topic} {mod}")
    return variations


def extract_urls_from_results(
    results: list[dict], platform: str
) -> list[str]:
    """Extract and deduplicate platform-specific URLs from search results.

    Args:
        results: List of search result dicts with "url" key
        platform: Platform to filter for

    Returns:
        List of unique, valid platform URLs
    """
    config = _PLATFORM_CONFIG.get(platform, {})
    site = config.get("site", "")
    if not site:
        return []

    seen = set()
    urls = []

    for result in results:
        url = result.get("url", "").strip()
        if not url or site not in url:
            continue

        url = _normalize_url(url, platform)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)

    return urls


def _normalize_url(url: str, platform: str) -> str:
    """Normalize a URL for a given platform."""
    if "?" in url:
        base = url.split("?")[0]
    else:
        base = url

    if "#" in base:
        base = base.split("#")[0]

    if platform == "youtube":
        if "/watch" in url or "/shorts/" in url:
            return url  # Keep full URL with video ID
        return ""

    if platform == "tiktok":
        if "/video/" in url or "/@" in url:
            return base
        return ""

    if platform == "facebook":
        if "/posts/" in url or "/reel/" in url or "/videos/" in url or "/watch" in url:
            return base
        # Also accept general Facebook page/group URLs for comment scraping
        if "facebook.com/" in url and url != f"https://www.{platform}.com/":
            return base
        return ""

    if platform == "instagram":
        if "/p/" in url or "/reel/" in url:
            return base
        return ""

    return base
