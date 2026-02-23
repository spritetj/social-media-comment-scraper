"""
Web search integration — find URLs via Google with full operator support.

Search backends (in order of priority):
1. Serper.dev API — lightweight REST, supports ALL Google operators
2. SerpAPI — alternative API
3. yt-dlp — direct YouTube search (no API key needed)
4. DuckDuckGo — free fallback (limited operator support)

Usage:
    Set SERPER_API_KEY or SERPAPI_KEY in environment or st.session_state.
    Get a free key at https://serper.dev (2,500 free queries).
"""

import os
import re
import html as html_lib
import time
import random
import asyncio
from urllib.parse import quote_plus, unquote

import requests


# ---------------------------------------------------------------------------
# Serper.dev (primary — lightweight, full Google operator support)
# ---------------------------------------------------------------------------

def _get_serper_key() -> str:
    """Get Serper API key from session state or environment."""
    try:
        import streamlit as st
        key = st.session_state.get("serper_api_key", "")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("SERPER_API_KEY", "")


def _get_serpapi_key() -> str:
    """Get SerpAPI key from session state or environment."""
    try:
        import streamlit as st
        key = st.session_state.get("serpapi_key", "")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("SERPAPI_KEY", "")


def _search_serper(query: str, max_results: int = 50, gl: str = "th", hl: str = "th") -> list[dict]:
    """Search Google via Serper.dev API with auto-pagination.

    Supports Google operators: site:, -inurl:, intitle:, after:, before:, "quotes".
    Note: intext: is NOT supported by Serper — use intitle: or "quotes" instead.

    Serper free tier returns 10 results per page. This function paginates
    automatically to collect up to max_results.
    """
    api_key = _get_serper_key()
    if not api_key:
        return []

    results = []
    seen_urls = set()
    per_page = 10  # Serper free tier limit per page
    max_pages = (max_results + per_page - 1) // per_page  # ceil division

    for page_num in range(1, max_pages + 1):
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                json={
                    "q": query,
                    "num": per_page,
                    "page": page_num,
                    "gl": gl,
                    "hl": hl,
                    "udm": 14,  # Google "Web" tab — returns only direct links
                },
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            page_results = []

            # Organic results
            for item in data.get("organic", []):
                url = item.get("link", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    page_results.append({
                        "url": url,
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                    })

            # Video results
            for item in data.get("videos", []):
                url = item.get("link", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    page_results.append({
                        "url": url,
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                    })

            if not page_results:
                break  # No more results available

            results.extend(page_results)

            if len(results) >= max_results:
                break

            # Small delay between pages
            if page_num < max_pages:
                time.sleep(random.uniform(0.2, 0.5))

        except Exception:
            break

    return results[:max_results]


def _search_serpapi(query: str, max_results: int = 20, gl: str = "th", hl: str = "th") -> list[dict]:
    """Search Google via SerpAPI.

    Supports ALL Google operators.
    """
    api_key = _get_serpapi_key()
    if not api_key:
        return []

    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "api_key": api_key,
                "num": max_results,
                "gl": gl,
                "hl": hl,
                "engine": "google",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("organic_results", []):
            results.append({
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
            })

        for item in data.get("video_results", []):
            url = item.get("link", "")
            if url and url not in {r["url"] for r in results}:
                results.append({
                    "url": url,
                    "title": item.get("title", ""),
                    "snippet": "",
                })

        return results[:max_results]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# YouTube direct search via yt-dlp (fast, no API key needed)
# ---------------------------------------------------------------------------

def search_youtube(topic: str, max_results: int = 15) -> list[dict]:
    """Search YouTube directly via yt-dlp."""
    try:
        import yt_dlp

        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f"ytsearch{max_results}:{topic}", download=False)
            entries = result.get("entries", [])

        return [
            {
                "url": e.get("url", ""),
                "title": e.get("title", ""),
                "snippet": e.get("description", "")[:200] if e.get("description") else "",
            }
            for e in entries
            if e.get("url", "").startswith("http")
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# DuckDuckGo fallback (free, no API key)
# ---------------------------------------------------------------------------

def _search_ddg(query: str, max_results: int = 20) -> list[dict]:
    """Search via DuckDuckGo (limited operator support)."""
    # Try library first
    try:
        import warnings
        warnings.filterwarnings("ignore", message=".*renamed.*")
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))

        if raw:
            return [
                {
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
                if r.get("href", "").startswith("http")
            ]
    except Exception:
        pass

    # Fallback: DDG HTML
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        results = []
        blocks = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            resp.text,
            re.DOTALL,
        )
        for href, title_html in blocks:
            uddg = re.search(r"uddg=([^&]+)", href)
            actual_url = unquote(uddg.group(1)) if uddg else href
            if "duckduckgo.com" in actual_url or not actual_url.startswith("http"):
                continue
            title = html_lib.unescape(re.sub(r"<[^>]+>", "", title_html).strip())
            results.append({"url": actual_url, "title": title, "snippet": ""})

        seen = set()
        return [r for r in results if r["url"] not in seen and not seen.add(r["url"])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Main search function (tries backends in order)
# ---------------------------------------------------------------------------

def search_google(
    query: str,
    max_results: int = 20,
    progress_callback=None,
    gl: str = "th",
    hl: str = "th",
) -> list[dict]:
    """Execute a Google search with full operator support.

    Tries: Serper.dev → SerpAPI → DuckDuckGo fallback.

    Args:
        query: Full Google query with operators (site:, intext:, after:, etc.)
        max_results: Maximum results
        progress_callback: Optional callback
        gl: Google country (default: "th" for Thailand)
        hl: Google language (default: "th" for Thai)

    Returns:
        List of {"url": str, "title": str, "snippet": str}
    """
    # Try Serper.dev first
    results = _search_serper(query, max_results, gl, hl)
    if results:
        if progress_callback:
            progress_callback(f"Found {len(results)} Google results (via Serper)")
        return results

    # Try SerpAPI
    results = _search_serpapi(query, max_results, gl, hl)
    if results:
        if progress_callback:
            progress_callback(f"Found {len(results)} Google results (via SerpAPI)")
        return results

    # Fallback to DDG (limited operator support)
    if progress_callback:
        progress_callback("No search API key configured — using DuckDuckGo fallback")
    results = _search_ddg(query, max_results)
    if results:
        if progress_callback:
            progress_callback(f"Found {len(results)} results (via DuckDuckGo)")
        return results

    if progress_callback:
        progress_callback("No results found — configure a Serper.dev API key in Settings for best results")
    return []


# ---------------------------------------------------------------------------
# Multi-platform search orchestration
# ---------------------------------------------------------------------------

def _extract_relevance_keywords(topic: str) -> list[str]:
    """Extract brand/entity keywords from topic for relevance filtering.

    Returns lowercase keywords that results must match against.
    """
    # English words (3+ chars, likely brand names)
    en_words = re.findall(r'[A-Za-z][A-Za-z0-9]{2,}', topic)
    en_stop = {"the", "and", "for", "how", "why", "what", "this", "that",
               "from", "with", "about", "does", "not", "but", "are", "was"}
    keywords = [w.lower() for w in en_words if w.lower() not in en_stop]
    # If no English keywords, use the whole topic (simple topic case)
    if not keywords:
        keywords = [topic.lower().strip()]
    return keywords


def _result_is_relevant(result: dict, keywords: list[str]) -> bool:
    """Check if a search result is relevant to the query keywords.

    Primary check: keyword in TITLE (strong signal).
    Secondary check: keyword in SNIPPET (weaker but valid — keeps results
    where the title is generic but the content clearly matches).
    """
    title = result.get("title", "").lower()
    if any(kw in title for kw in keywords):
        return True
    snippet = result.get("snippet", "").lower()
    return any(kw in snippet for kw in keywords)


def search_multi_queries(
    queries: dict[str, list[str]],
    max_results_per_query: int = 50,
    progress_callback=None,
    topic: str = "",
    gl: str = "th",
    hl: str = "th",
    target_urls_per_platform: int = 50,
    relevance_keywords: list[str] | None = None,
) -> dict[str, list[dict]]:
    """Search across multiple platforms using multiple query variations.

    Combines yt-dlp (for YouTube) with Google search (for all platforms)
    to maximize unique URL discovery. Stops searching a platform once
    target_urls_per_platform unique URLs are found.

    All results are filtered for relevance: title or snippet must contain
    at least one primary keyword (brand/entity name) from the topic.

    Args:
        queries: {platform: [query1, query2, ...]} with Google dork queries
        max_results_per_query: Max results requested per individual query
        progress_callback: Optional callback
        topic: Original search topic (used for YouTube yt-dlp search)
        gl: Google country code
        hl: Google language code
        target_urls_per_platform: Stop after finding this many unique URLs
        relevance_keywords: Pre-built keywords (including Thai variants) for
            relevance filtering. Falls back to _extract_relevance_keywords(topic).
    """
    all_results = {}
    if not relevance_keywords:
        relevance_keywords = _extract_relevance_keywords(topic)

    for platform in queries:
        if progress_callback:
            progress_callback(f"Searching {platform.title()}...")

        platform_results = []
        seen_urls = set()

        # YouTube: start with yt-dlp using keywords, not full question
        if platform == "youtube" and topic:
            # Use extracted keywords for yt-dlp, not raw question
            yt_topic = " ".join(relevance_keywords) if relevance_keywords else topic
            yt_results = search_youtube(yt_topic, max_results=30)
            for r in yt_results:
                # Strict filter for yt-dlp: keyword must be in TITLE
                # (yt-dlp snippets are truncated descriptions, unreliable)
                title_lower = r.get("title", "").lower()
                if r["url"] not in seen_urls and any(kw in title_lower for kw in relevance_keywords):
                    seen_urls.add(r["url"])
                    platform_results.append(r)
            if progress_callback and platform_results:
                progress_callback(f"Found {len(platform_results)} YouTube videos via yt-dlp")

        # Google search with dork operators for ALL platforms (including YouTube)
        # This supplements yt-dlp results and is the primary source for other platforms
        for query in queries.get(platform, []):
            # Skip if we already have enough
            if len(platform_results) >= target_urls_per_platform:
                break

            if progress_callback:
                display_q = query[:120]
                progress_callback(f"Query: {display_q}")

            results = search_google(
                query,
                max_results=max_results_per_query,
                progress_callback=None,  # Don't spam per-query messages
                gl=gl,
                hl=hl,
            )
            new_count = 0
            for r in results:
                if r["url"] not in seen_urls and _result_is_relevant(r, relevance_keywords):
                    seen_urls.add(r["url"])
                    platform_results.append(r)
                    new_count += 1

            if progress_callback and new_count:
                progress_callback(
                    f"{platform.title()}: +{new_count} new URLs (total: {len(platform_results)})"
                )
                for item in platform_results[-new_count:][:3]:
                    title = item.get('title', '')[:80]
                    if title:
                        progress_callback(f"  → {title}")

            # Rate limiting between queries
            time.sleep(random.uniform(0.3, 0.8))

        all_results[platform] = platform_results
        if progress_callback:
            progress_callback(f"Total {platform.title()}: {len(platform_results)} unique URLs found")

    return all_results
