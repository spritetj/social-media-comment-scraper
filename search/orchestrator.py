"""
Multi-platform scraping orchestrator — coordinates scraping across platforms.
"""

import asyncio
import time


async def scrape_platform_urls(
    platform: str,
    urls: list[str],
    cookies: dict | list | None = None,
    progress_callback=None,
    max_comments_per_url: int = 200,
) -> list[dict]:
    """Scrape comments from a list of URLs for a single platform.

    Args:
        platform: "youtube", "tiktok", "facebook", "instagram"
        urls: List of URLs to scrape
        cookies: Platform-specific cookies (if needed)
        progress_callback: Progress callback function
        max_comments_per_url: Max comments to fetch per URL

    Returns:
        List of raw comment dicts
    """
    if not urls:
        return []

    all_comments = []

    if platform == "youtube":
        all_comments = await _scrape_youtube(urls, cookies, progress_callback, max_comments_per_url)
    elif platform == "tiktok":
        all_comments = await _scrape_tiktok(urls, progress_callback, max_comments_per_url)
    elif platform == "facebook":
        all_comments = await _scrape_facebook(urls, cookies, progress_callback)
    elif platform == "instagram":
        all_comments = await _scrape_instagram(urls, cookies, progress_callback)

    return all_comments


async def _scrape_youtube(urls, cookies, callback, max_comments):
    """Scrape YouTube comments from multiple URLs."""
    try:
        from scrapers.youtube import YouTubeCommentScraper
    except ImportError:
        if callback:
            callback("YouTube scraper not available")
        return []

    scraper = YouTubeCommentScraper(
        headless=True,
        max_comments=max_comments,
        max_replies=5,
        sort_by="top",
        progress_callback=callback,
    )
    if cookies:
        scraper.set_cookies(cookies if isinstance(cookies, dict) else {})

    comments = []
    seen_ids = set()
    for i, url in enumerate(urls):
        if callback:
            callback(f"YouTube {i+1}/{len(urls)}: {url[:60]}...")
        try:
            result = await scraper.scrape_video_comments(url, seen_ids=seen_ids)
            if result:
                comments.extend(result)
                if callback:
                    callback(f"Got {len(result)} comments from YouTube video")
        except Exception:
            if callback:
                callback(f"Failed to scrape YouTube video {i+1}")
        await asyncio.sleep(1.0)

    return comments


async def _scrape_tiktok(urls, callback, max_comments):
    """Scrape TikTok comments from multiple URLs."""
    try:
        from scrapers.tiktok import TikTokCommentScraper
    except ImportError:
        if callback:
            callback("TikTok scraper not available")
        return []

    scraper = TikTokCommentScraper(
        headless=True,
        max_comments=max_comments,
        max_replies=3,
        progress_callback=callback,
    )

    comments = []
    seen_ids = set()
    for i, url in enumerate(urls):
        if callback:
            callback(f"TikTok {i+1}/{len(urls)}: {url[:60]}...")
        try:
            result = await scraper.scrape_video_comments(url, seen_ids=seen_ids)
            if result:
                comments.extend(result)
                if callback:
                    callback(f"Got {len(result)} comments from TikTok video")
        except Exception:
            if callback:
                callback(f"Failed to scrape TikTok video {i+1}")
        await asyncio.sleep(1.0)

    return comments


async def _scrape_facebook(urls, cookies, callback):
    """Scrape Facebook comments from multiple URLs."""
    if not cookies:
        if callback:
            callback("Facebook requires cookies — skipping")
        return []

    try:
        from scrapers.facebook import scrape_comments_fast
    except ImportError:
        if callback:
            callback("Facebook scraper not available")
        return []

    comments = []
    seen_ids = set()
    for i, url in enumerate(urls):
        if callback:
            callback(f"Facebook {i+1}/{len(urls)}: {url[:60]}...")
        try:
            result = await scrape_comments_fast(url, cookies=cookies, progress_callback=callback, seen_ids=seen_ids)
            if result:
                comments.extend(result)
                if callback:
                    callback(f"Got {len(result)} comments from Facebook post")
        except Exception:
            if callback:
                callback(f"Failed to scrape Facebook post {i+1}")
        await asyncio.sleep(1.5)

    return comments


async def _scrape_instagram(urls, cookies, callback):
    """Scrape Instagram comments from multiple URLs."""
    try:
        from scrapers.instagram import scrape_post_urls
    except ImportError:
        if callback:
            callback("Instagram scraper not available")
        return []

    if callback:
        callback(f"Scraping {len(urls)} Instagram posts...")

    try:
        seen_ids = set()
        comments = await scrape_post_urls(urls, cookies=cookies, progress_callback=callback, seen_ids=seen_ids)
        return comments or []
    except Exception:
        if callback:
            callback("Failed to scrape Instagram posts")
        return []


async def scrape_all_platforms(
    url_map: dict[str, list[str]],
    cookies_map: dict[str, dict | list | None] | None = None,
    progress_callback=None,
    max_comments_per_url: int = 200,
) -> dict[str, list[dict]]:
    """Scrape comments across all platforms.

    Args:
        url_map: {platform: [url1, url2, ...]}
        cookies_map: {platform: cookies} for platforms requiring auth
        progress_callback: Progress callback function
        max_comments_per_url: Max comments per URL

    Returns:
        {platform: [comment_dicts]}
    """
    if cookies_map is None:
        cookies_map = {}

    results = {}

    for platform, urls in url_map.items():
        if not urls:
            continue

        if progress_callback:
            progress_callback(f"Scraping {len(urls)} {platform.title()} URLs...")

        cookies = cookies_map.get(platform)
        platform_comments = await scrape_platform_urls(
            platform=platform,
            urls=urls,
            cookies=cookies,
            progress_callback=progress_callback,
            max_comments_per_url=max_comments_per_url,
        )
        results[platform] = platform_comments

        if progress_callback:
            progress_callback(
                f"Finished {platform.title()}: {len(platform_comments)} comments"
            )

    return results
