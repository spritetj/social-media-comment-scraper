"""
End-to-end One Search pipeline — query expansion, URL discovery,
multi-platform scraping, normalization, analysis, and AI insights.

Provides both:
  - run_one_search(): monolithic pipeline (backward compat)
  - step_generate_queries / step_search_urls / step_scrape_and_analyze:
    individual steps for the interactive step-by-step workflow
"""

import asyncio
from collections import Counter

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
        "search_results_detail": {},
        "url_map_detail": {},
        "scrape_log": [],
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
    result["search_results_detail"] = search_results

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

    # Build url_map_detail with titles from search results
    url_map_detail = {}
    for platform in platforms:
        title_lookup = {r["url"]: r.get("title", "") for r in search_results.get(platform, [])}
        url_map_detail[platform] = [
            {"url": url, "title": title_lookup.get(url, "")}
            for url in url_map[platform]
        ]
    result["url_map_detail"] = url_map_detail

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

    # Build scrape log: per-URL outcome
    from collections import Counter
    url_comment_counts = Counter(c.get("source_url", "") for c in all_clean if c.get("source_url"))
    scrape_log = []
    for platform, details in url_map_detail.items():
        for d in details:
            count = url_comment_counts.get(d["url"], 0)
            scrape_log.append({
                "platform": platform,
                "url": d["url"],
                "title": d["title"],
                "comment_count": count,
                "status": "ok" if count > 0 else "empty",
            })
    result["scrape_log"] = scrape_log

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


# ---------------------------------------------------------------------------
# Step functions for interactive workflow
# ---------------------------------------------------------------------------


async def step_generate_queries(
    topic: str,
    platforms: list[str],
    date_range: str = "any",
    progress_callback=None,
) -> dict:
    """Step 1: Generate search queries using LLM or rule-based fallback.

    Returns:
        {
            "queries": {platform: [query_strings]},
            "relevance_keywords": [str],
            "research_question": str,
            "hypotheses": [str],
        }
    """
    if progress_callback:
        progress_callback("Building search queries...")

    relevance_keywords = []
    research_question = ""
    hypotheses = []

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
        research_question = iq_result.research_question
        hypotheses = iq_result.hypotheses
    except Exception:
        queries = build_queries(topic, platforms, date_range)

    return {
        "queries": queries,
        "relevance_keywords": relevance_keywords,
        "research_question": research_question,
        "hypotheses": hypotheses,
    }


def step_search_urls(
    queries: dict[str, list[str]],
    platforms: list[str],
    max_urls_per_platform: int = 15,
    topic: str = "",
    relevance_keywords: list[str] | None = None,
    progress_callback=None,
) -> dict:
    """Step 2: Search Google for URLs using the generated queries.

    Returns:
        {
            "search_results": {platform: [{url, title, snippet}]},
            "url_map_detail": {platform: [{url, title}]},
        }
    """
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
    url_map = {}
    for platform in platforms:
        platform_results = search_results.get(platform, [])
        urls = extract_urls_from_results(platform_results, platform)
        if not urls:
            urls = [r["url"] for r in platform_results if r.get("url", "").startswith("http")]
        url_map[platform] = urls[:max_urls_per_platform]

    # Build url_map_detail with titles
    url_map_detail = {}
    for platform in platforms:
        title_lookup = {r["url"]: r.get("title", "") for r in search_results.get(platform, [])}
        url_map_detail[platform] = [
            {"url": url, "title": title_lookup.get(url, "")}
            for url in url_map[platform]
        ]

    total_urls = sum(len(urls) for urls in url_map.values())
    if progress_callback:
        url_summary = ", ".join(
            f"{len(urls)} {p.title()}" for p, urls in url_map.items() if urls
        )
        progress_callback(f"Found {total_urls} URLs: {url_summary}")

    return {
        "search_results": search_results,
        "url_map_detail": url_map_detail,
    }


async def step_scrape_and_analyze(
    url_map: dict[str, list[str]],
    platforms: list[str],
    cookies_map: dict | None = None,
    max_comments_per_url: int = 200,
    topic: str = "",
    progress_callback=None,
) -> dict:
    """Step 3: Scrape comments, normalize, analyze, and generate AI insight.

    Args:
        url_map: {platform: [url_strings]} — only selected URLs
        platforms: list of platform names
        cookies_map: {platform: cookies} for auth-required platforms
        max_comments_per_url: max comments per URL
        topic: original search topic
        progress_callback: callback

    Returns:
        Full result dict with comments_raw, comments_clean, analysis,
        customer_insight, scrape_log, etc.
    """
    result = {
        "topic": topic,
        "platforms": platforms,
        "comments_raw": {},
        "comments_clean": [],
        "total_comments": 0,
        "total_urls_scraped": 0,
        "scrape_log": [],
        "analysis": None,
        "customer_insight": None,
        "comment_tags": None,
        "tag_summary": None,
    }

    total_urls = sum(len(urls) for urls in url_map.values())
    if total_urls == 0:
        if progress_callback:
            progress_callback("No URLs to scrape.")
        return result

    # Scrape comments
    if progress_callback:
        progress_callback("Scraping comments across platforms...")

    raw_comments = await scrape_all_platforms(
        url_map=url_map,
        cookies_map=cookies_map,
        progress_callback=progress_callback,
        max_comments_per_url=max_comments_per_url,
    )
    result["comments_raw"] = raw_comments

    # Normalize
    if progress_callback:
        progress_callback("Normalizing comments...")

    all_clean = []
    for platform, comments in raw_comments.items():
        if comments:
            normalized = normalize_comments(comments, platform)
            all_clean.extend(normalized)

    result["comments_clean"] = all_clean
    result["total_comments"] = len(all_clean)
    result["total_urls_scraped"] = total_urls

    # Build scrape log
    url_comment_counts = Counter(
        c.get("source_url", "") for c in all_clean if c.get("source_url")
    )
    scrape_log = []
    for platform, urls in url_map.items():
        for url in urls:
            count = url_comment_counts.get(url, 0)
            scrape_log.append({
                "platform": platform,
                "url": url,
                "title": "",
                "comment_count": count,
                "status": "ok" if count > 0 else "empty",
            })
    result["scrape_log"] = scrape_log

    if progress_callback:
        progress_callback(f"Collected {len(all_clean)} total comments")

    # Run analysis (if enough comments)
    if len(all_clean) >= 10:
        if progress_callback:
            progress_callback("Running analysis...")
        try:
            from analysis.pipeline import run_full_analysis
            result["analysis"] = run_full_analysis(all_clean)
        except Exception as e:
            if progress_callback:
                progress_callback(f"Analysis error: {e}")

    # Detect analysis provider
    provider = _detect_analysis_provider()

    if provider == "notebooklm":
        # --- NotebookLM path: VADER sentiment + skip per-comment LLM tagging ---
        if len(all_clean) >= 5:
            if progress_callback:
                progress_callback("Applying sentiment analysis (VADER)...")
            _apply_vader_tags(all_clean, result.get("analysis", {}))
            result["comments_clean"] = all_clean
            result["tag_summary"] = _vader_tag_summary(all_clean)
            if progress_callback:
                progress_callback("Sentiment tagging complete (VADER).")
        # NotebookLM corpus-level insight is generated separately via the
        # NLM setup step in the One Search UI (not here in the pipeline).
        # The pipeline just prepares VADER tags for immediate use.

    else:
        # --- Paid API path: per-comment LLM tagging + insight report ---

        # LLM Comment Tagging (if LLM available)
        if len(all_clean) >= 5:
            try:
                from analysis.llm_tagger import tag_comments, merge_tags_into_comments, aggregate_tags

                if progress_callback:
                    progress_callback("Running AI comment tagging...")
                tags = await tag_comments(all_clean, progress_callback=progress_callback)
                all_clean = merge_tags_into_comments(all_clean, tags)
                result["comments_clean"] = all_clean
                result["comment_tags"] = tags
                result["tag_summary"] = aggregate_tags(all_clean)
                if progress_callback:
                    progress_callback("AI tagging complete.")
            except Exception as e:
                if progress_callback:
                    progress_callback(f"AI tagging skipped: {e}")

        # Generate AI Customer Insight Report
        if len(all_clean) >= 5:
            if progress_callback:
                progress_callback("Generating AI Customer Insight Report...")
            try:
                from ai.client import LLMClient
                from ai.prompts import format_comments_for_prompt, CUSTOMER_INSIGHT_REPORT

                platforms_str = ", ".join(platforms)
                formatted = format_comments_for_prompt(all_clean[:500])  # cap for token limit

                # Enrich prompt with tag summary if available
                tag_context = ""
                if result.get("tag_summary"):
                    ts = result["tag_summary"]
                    tag_context = (
                        f"\n\nAI TAG SUMMARY (pre-classified data):\n"
                        f"Sentiment: {ts.get('sentiment_distribution', {})}\n"
                        f"Emotions: {ts.get('emotion_distribution', {})}\n"
                        f"Intents: {ts.get('intent_distribution', {})}\n"
                        f"Urgency: {ts.get('urgency_distribution', {})}\n"
                        f"Aspect-Sentiment: {ts.get('aspect_sentiment', {})}\n"
                        f"Use this pre-classified data to ground your analysis with precise numbers.\n"
                    )

                prompt = CUSTOMER_INSIGHT_REPORT.format(
                    comment_count=len(all_clean),
                    topic=topic,
                    platforms=platforms_str,
                    comments=formatted + tag_context,
                )
                client = LLMClient()
                insight = await client.analyze(prompt=prompt)
                result["customer_insight"] = insight
            except Exception as e:
                if progress_callback:
                    progress_callback(f"AI Insight error: {e}")

    return result


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


def _detect_analysis_provider() -> str | None:
    """Check session state for the active analysis provider."""
    try:
        import streamlit as st
        return st.session_state.get("active_provider")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# VADER-based sentiment tagging (free, local)
# ---------------------------------------------------------------------------


def _apply_vader_tags(comments: list[dict], analysis: dict | None):
    """Apply VADER-based ai_sentiment to each comment (free, local).

    Maps VADER compound scores to ai_sentiment labels:
      compound >= 0.05 -> "positive"
      compound <= -0.05 -> "negative"
      else -> "neutral"
    """
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        sid = SentimentIntensityAnalyzer()
    except ImportError:
        # Fallback to nltk's VADER if available
        try:
            from nltk.sentiment.vader import SentimentIntensityAnalyzer
            sid = SentimentIntensityAnalyzer()
        except Exception:
            # No VADER available — skip tagging
            return

    for c in comments:
        text = c.get("text", "")
        if not text:
            c["ai_sentiment"] = "neutral"
            continue
        scores = sid.polarity_scores(text)
        compound = scores["compound"]
        if compound >= 0.05:
            c["ai_sentiment"] = "positive"
        elif compound <= -0.05:
            c["ai_sentiment"] = "negative"
        else:
            c["ai_sentiment"] = "neutral"


def _vader_tag_summary(comments: list[dict]) -> dict:
    """Build a minimal tag_summary from VADER-tagged comments."""
    from collections import Counter
    sent_counts = Counter(c.get("ai_sentiment", "neutral") for c in comments)
    total = len(comments) or 1
    return {
        "sentiment_distribution": {
            "positive": round(sent_counts.get("positive", 0) / total * 100, 1),
            "negative": round(sent_counts.get("negative", 0) / total * 100, 1),
            "neutral": round(sent_counts.get("neutral", 0) / total * 100, 1),
        },
        "aspect_sentiment": {},
        "emotion_distribution": {},
        "intent_distribution": {},
        "urgency_distribution": {},
    }
