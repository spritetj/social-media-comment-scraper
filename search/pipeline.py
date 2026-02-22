"""
End-to-end One Search pipeline — query expansion, URL discovery,
multi-platform scraping, normalization, analysis, and AI insights.
"""

import asyncio

from search.query_builder import build_queries, extract_urls_from_results
from search.google_search import search_multi_queries
from search.orchestrator import scrape_all_platforms
from utils.schema import normalize_comments


async def run_one_search(
    topic: str,
    platforms: list[str] | None = None,
    date_range: str = "any",
    max_urls_per_platform: int = 15,
    max_comments_per_url: int = 200,
    cookies_map: dict | None = None,
    progress_callback=None,
) -> dict:
    """Run the full One Search pipeline.

    Args:
        topic: Search topic (e.g., "Tesla Model 3")
        platforms: Platforms to search (default: all)
        date_range: "week", "month", "year", or "any"
        max_urls_per_platform: Max URLs to scrape per platform
        max_comments_per_url: Max comments per individual URL
        cookies_map: {platform: cookies} for auth-required platforms
        progress_callback: Progress callback

    Returns:
        {
            "topic": str,
            "platforms": list,
            "queries": {platform: [queries]},
            "urls_found": {platform: [urls]},
            "comments_raw": {platform: [comments]},
            "comments_clean": [all normalized comments],
            "total_comments": int,
            "total_urls_scraped": int,
            "analysis": dict or None,
        }
    """
    if platforms is None:
        platforms = ["youtube", "tiktok", "facebook", "instagram"]

    result = {
        "topic": topic,
        "platforms": platforms,
        "queries": {},
        "urls_found": {},
        "comments_raw": {},
        "comments_clean": [],
        "total_comments": 0,
        "total_urls_scraped": 0,
        "analysis": None,
    }

    # Step 1: Build search queries
    if progress_callback:
        progress_callback("Building search queries...")

    relevance_keywords = None
    try:
        from search.intelligent_query_builder import build_intelligent_queries
        iq_result = await build_intelligent_queries(
            user_input=topic,
            platforms=platforms,
            date_range=date_range,
            progress_callback=progress_callback,
        )
        queries = iq_result.queries
        relevance_keywords = iq_result.relevance_keywords
    except Exception:
        queries = build_queries(topic, platforms, date_range)
    result["queries"] = queries

    # Step 2: Search Google for URLs
    if progress_callback:
        progress_callback("Searching for relevant content...")

    search_results = search_multi_queries(
        queries,
        max_results_per_query=max_urls_per_platform,
        progress_callback=progress_callback,
        topic=topic,
        relevance_keywords=relevance_keywords,
    )

    # Extract and filter URLs per platform
    # For platforms with direct search (YouTube), URLs are already valid
    url_map = {}
    for platform in platforms:
        platform_results = search_results.get(platform, [])
        # Try extracting platform-specific URLs first
        urls = extract_urls_from_results(platform_results, platform)
        # If no platform-filtered URLs, use raw URLs (direct search results)
        if not urls:
            urls = [r["url"] for r in platform_results if r.get("url", "").startswith("http")]
        url_map[platform] = urls[:max_urls_per_platform]

    result["urls_found"] = {p: len(urls) for p, urls in url_map.items()}

    total_urls = sum(len(urls) for urls in url_map.values())
    if progress_callback:
        url_summary = ", ".join(
            f"{len(urls)} {p.title()}" for p, urls in url_map.items() if urls
        )
        progress_callback(f"Found {total_urls} URLs: {url_summary}")

    if total_urls == 0:
        if progress_callback:
            progress_callback("No relevant URLs found. Try a different search topic.")
        return result

    # Step 3: Scrape comments from all platforms
    if progress_callback:
        progress_callback("Scraping comments across platforms...")

    raw_comments = await scrape_all_platforms(
        url_map=url_map,
        cookies_map=cookies_map,
        progress_callback=progress_callback,
        max_comments_per_url=max_comments_per_url,
    )
    result["comments_raw"] = raw_comments

    # Step 4: Normalize all comments
    if progress_callback:
        progress_callback("Normalizing comments...")

    all_clean = []
    for platform, comments in raw_comments.items():
        if comments:
            normalized = normalize_comments(comments, platform)
            all_clean.extend(normalized)

    result["comments_clean"] = all_clean
    result["total_comments"] = len(all_clean)
    result["total_urls_scraped"] = sum(
        1 for urls in url_map.values() for _ in urls
    )

    if progress_callback:
        progress_callback(f"Collected {len(all_clean)} total comments")

    # Step 5: Run analysis (if enough comments)
    if len(all_clean) >= 10:
        if progress_callback:
            progress_callback("Running analysis...")

        try:
            from analysis.pipeline import run_full_analysis
            result["analysis"] = run_full_analysis(all_clean)
        except Exception as e:
            if progress_callback:
                progress_callback(f"Analysis error: {e}")

    return result
