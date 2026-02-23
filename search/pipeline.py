"""
End-to-end One Search pipeline — query expansion, URL discovery,
multi-platform scraping, normalization, analysis, and AI insights.

Provides both:
  - run_one_search(): monolithic pipeline (backward compat)
  - step_generate_queries / step_search_urls / step_scrape_and_analyze:
    individual steps for the interactive step-by-step workflow
"""

import asyncio
import re
from collections import Counter

from search.query_builder import build_queries, extract_urls_from_results
from search.google_search import search_multi_queries
from search.orchestrator import scrape_all_platforms
from utils.schema import normalize_comments


# ---------------------------------------------------------------------------
# Content-topic matching (Layer 3 validation)
# ---------------------------------------------------------------------------

# Common stop words to ignore when matching content to topic
_STOP_WORDS = frozenset({
    # English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "and", "or", "but", "not", "no", "it", "this", "that", "my", "your",
    "we", "they", "he", "she", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "have", "has", "had",
    "about", "how", "what", "when", "where", "who", "which", "why",
    # Thai particles
    "จาก", "ของ", "ที่", "ใน", "และ", "หรือ", "แต่", "ก็", "ได้",
    "ไม่", "มี", "เป็น", "กับ", "แล้ว", "ยัง", "ไป", "มา", "อยู่",
    "คือ", "นี้", "นั้น", "ให้", "กัน", "จะ", "ว่า",
})


def _content_matches_topic(content_title: str, topic: str) -> tuple[bool, float]:
    """Check if scraped content_title matches the search topic.

    Uses simple token overlap. Handles mixed Thai/English via space-split.

    Returns:
        (is_match, score) where score is the fraction of topic tokens found.
        Empty content_title → (True, 0.0) because we can't verify.
    """
    if not content_title or not content_title.strip():
        return True, 0.0
    if not topic or not topic.strip():
        return True, 0.0

    def _tokenize(text: str) -> set[str]:
        tokens = re.split(r'\s+', text.lower().strip())
        return {t for t in tokens if len(t) >= 2 and t not in _STOP_WORDS}

    topic_tokens = _tokenize(topic)
    if not topic_tokens:
        return True, 0.0

    content_tokens = _tokenize(content_title)
    matched = topic_tokens & content_tokens
    score = len(matched) / len(topic_tokens)
    return score >= 0.3, score


# Platform-specific field names for extracting post content info
_CONTENT_TITLE_FIELDS = {
    "facebook": "postCaption",
    "youtube": "videoTitle",
    "tiktok": "video_caption",
    "instagram": "captionText",
}

_SOURCE_URL_FIELDS = {
    "facebook": "facebookUrl",
    "youtube": "youtubeUrl",
    "tiktok": "tiktokUrl",
    "instagram": "instagramUrl",
}


def _build_enhanced_scrape_log(
    url_map: dict,
    all_clean: list[dict],
    raw_comments: dict,
    topic: str,
    url_titles: dict | None = None,
) -> list[dict]:
    """Build scrape log with content validation and warnings.

    Args:
        url_map: {platform: [urls]} or {platform: [{url, title}]}
        all_clean: normalized comments
        raw_comments: {platform: [raw_comment_dicts]} from scrapers
        topic: original search topic
        url_titles: optional {url: google_search_title} lookup

    Returns:
        List of enhanced scrape_log entries.
    """
    url_titles = url_titles or {}

    # Count normalized comments per source_url
    url_comment_counts = Counter(
        c.get("source_url", "") for c in all_clean if c.get("source_url")
    )

    # Extract content titles and scrape warnings from raw comments per URL
    url_content_titles: dict[str, str] = {}
    url_warnings: dict[str, list[str]] = {}

    for platform, comments in raw_comments.items():
        title_field = _CONTENT_TITLE_FIELDS.get(platform, "")
        url_field = _SOURCE_URL_FIELDS.get(platform, "")

        for c in comments:
            if not isinstance(c, dict):
                continue

            src_url = c.get(url_field, "") or c.get("inputUrl", "") or c.get("source_url", "")
            if not src_url:
                continue

            # Extract content title (take first non-empty)
            if src_url not in url_content_titles and title_field:
                ct = c.get(title_field, "")
                if ct and isinstance(ct, str) and ct.strip():
                    url_content_titles[src_url] = ct.strip()[:200]

            # Extract Facebook scrape warnings
            if platform == "facebook" and src_url not in url_warnings:
                warnings = []
                if c.get("_redirect_detected"):
                    final = c.get("_final_url", "")
                    warnings.append(f"Redirect detected → {final[:60]}")
                if c.get("_feed_page_detected"):
                    n = c.get("_total_feedback_ids", 0)
                    warnings.append(f"Feed page detected ({n} posts)")
                strategy = c.get("_feedback_id_strategy", "")
                if strategy == "heuristic" and c.get("_feed_page_detected"):
                    warnings.append("Post selected by heuristic (may be wrong)")
                if warnings:
                    url_warnings[src_url] = warnings

    # Build log entries
    scrape_log = []
    for platform, urls_or_details in url_map.items():
        for item in urls_or_details:
            if isinstance(item, dict):
                url = item.get("url", "")
                google_title = item.get("title", "")
            else:
                url = item
                google_title = url_titles.get(url, "")

            count = url_comment_counts.get(url, 0)
            content_title = url_content_titles.get(url, "")
            warnings = url_warnings.get(url, [])

            # Content match validation
            content_match, match_score = _content_matches_topic(content_title, topic)

            scrape_log.append({
                "platform": platform,
                "url": url,
                "title": google_title,
                "content_title": content_title,
                "comment_count": count,
                "status": "ok" if count > 0 else "empty",
                "warnings": warnings,
                "content_match": content_match,
            })

    return scrape_log


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
        target_urls_per_platform=max_urls_per_platform,
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

    # Build enhanced scrape log with content validation
    result["scrape_log"] = _build_enhanced_scrape_log(
        url_map=url_map_detail,
        all_clean=all_clean,
        raw_comments=raw_comments,
        topic=topic,
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
        target_urls_per_platform=max_urls_per_platform,
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

    # Build enhanced scrape log with content validation
    result["scrape_log"] = _build_enhanced_scrape_log(
        url_map={p: urls for p, urls in url_map.items()},
        all_clean=all_clean,
        raw_comments=raw_comments,
        topic=topic,
    )

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
                progress_callback("Analyzing sentiment...")
            _apply_vader_tags(all_clean, result.get("analysis", {}))
            result["comments_clean"] = all_clean
            result["tag_summary"] = _vader_tag_summary(all_clean)
            if progress_callback:
                progress_callback("Sentiment analysis complete.")
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
                    progress_callback("Categorizing comments...")
                tags = await tag_comments(all_clean, progress_callback=progress_callback)
                all_clean = merge_tags_into_comments(all_clean, tags)
                result["comments_clean"] = all_clean
                result["comment_tags"] = tags
                result["tag_summary"] = aggregate_tags(all_clean)
                if progress_callback:
                    progress_callback("Categorization complete.")
            except Exception as e:
                if progress_callback:
                    progress_callback(f"Categorization skipped: {e}")

        # Generate AI Customer Insight Report
        if len(all_clean) >= 5:
            if progress_callback:
                progress_callback("Generating insight report...")
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
                    progress_callback(f"Insight report error: {e}")

    return result


# ---------------------------------------------------------------------------
# NLM-powered query generation (via shared notebook)
# ---------------------------------------------------------------------------

async def step_generate_queries_nlm(
    topic: str,
    platforms: list[str],
) -> dict:
    """Generate search queries using the shared NotebookLM notebook.

    Uses 1 NLM query from the daily budget.

    Returns same shape as step_generate_queries:
        {"queries": {platform: [query1, query2, ...]}}
    """
    from ai.notebooklm_bridge import get_bridge, NotebookLMBridge, QUERY_GEN_NOTEBOOK_ID

    bridge = get_bridge()

    prompt = (
        f'ถ้า users พิมพ์ "{topic}" เป็นคำค้นหาบน Google '
        'จะมีความเป็นไปได้อะไรอีกบ้างที่คนจะค้นหาอีก '
        'ตอบมา 10 คำที่มีความน่าจะเป็นมากที่สุด เลยไม่ต้องอธิบาย '
        'ถึงแม้ไม่มีแหล่งข้อมูลก็ตาม โฟกัสที่คน ค้นหาเป็นคนไทย'
    )

    answer, _ = await bridge.ask_question(
        question=prompt,
        notebook_id=QUERY_GEN_NOTEBOOK_ID,
    )
    NotebookLMBridge.increment_usage(1)

    parsed = _parse_nlm_query_response(answer, platforms)
    return {"queries": parsed}


def _parse_nlm_query_response(response: str, platforms: list[str]) -> dict:
    """Parse NLM markdown response into {platform: [queries]}.

    Handles:
      - Headers like ## YouTube, **YouTube**, YouTube:
      - Bullet points (- query, * query, • query) and numbered lists (1. query)
      - Strips Google operators (site:, after:, before:) since they get
        added back by _restore_operators()
      - Skips intro/explanatory paragraphs NLM may prepend
    """
    platform_aliases = {
        "youtube": "youtube", "yt": "youtube",
        "tiktok": "tiktok", "tik tok": "tiktok",
        "facebook": "facebook", "fb": "facebook",
        "instagram": "instagram", "ig": "instagram", "insta": "instagram",
    }
    requested = set(platforms)

    result = {p: [] for p in platforms}
    current_platform = None

    for line in response.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Check if line is a bullet/list item FIRST (before header detection)
        # to avoid misidentifying "• Yoguruto TikTok" as a TikTok header.
        # Require whitespace after marker to avoid matching **bold** headers.
        is_bullet = bool(re.match(r'^(?:[-•]\s+|\*\s+|\d+[.)]\s+)', stripped))

        if is_bullet:
            query = _extract_query_text(stripped)
            if query and current_platform:
                query = _strip_google_operators(query)
                if query:
                    result[current_platform].append(query)
        else:
            # Non-bullet line — check if it's a platform header
            detected = _detect_platform_header(stripped, platform_aliases, requested)
            if detected:
                current_platform = detected
            # Otherwise skip (intro text, explanations, etc.)

    # Fallback: if no platform sections found, collect ALL bullet items
    # and distribute to all requested platforms
    total_queries = sum(len(v) for v in result.values())
    if total_queries == 0:
        all_queries = []
        for line in response.splitlines():
            stripped = line.strip()
            q = _extract_query_text(stripped)
            if q:
                q = _strip_google_operators(q)
                if q:
                    all_queries.append(q)
        if all_queries:
            for p in platforms:
                result[p] = list(all_queries)

    return result


def _detect_platform_header(
    line: str, aliases: dict, requested: set[str]
) -> str | None:
    """Detect if a line is a platform section header.

    Only matches short header-like lines (## YouTube, **TikTok**, Facebook:).
    Skips long lines that happen to contain a platform name.
    """
    # Skip lines that are too long to be headers (likely explanatory text)
    if len(line) > 60:
        return None

    # Remove markdown formatting: ##, **, :
    clean = re.sub(r'^#{1,4}\s*', '', line)
    clean = re.sub(r'\*\*', '', clean)
    clean = clean.rstrip(':').strip().lower()

    # The cleaned header should be short (just the platform name, maybe a word or two)
    if len(clean) > 30:
        return None

    for alias, canonical in aliases.items():
        if alias in clean and canonical in requested:
            return canonical
    return None


def _extract_query_text(line: str) -> str:
    """Extract query text from a bullet or numbered list line."""
    # Match: - query, * query, • query, 1. query, 1) query
    # Require whitespace after marker to avoid matching **bold** headers.
    m = re.match(r'^(?:[-•]\s+|\*\s+|\d+[.)]\s+)', line)
    if not m:
        return ""

    text = line[m.end():].strip()
    if not text:
        return ""

    # Strip markdown bold markers: **text** → text
    text = text.replace("**", "")

    # Strip NLM citation brackets: [1], [1-3], [1, 3], [1, 2, 3]
    text = re.sub(r'\s*\[[\d,\s–-]+\]', '', text)

    # Strip surrounding quotes
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    elif len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        text = text[1:-1].strip()

    # Strip trailing explanations after — or --(space) or (...)
    text = re.split(r'\s+[—–]\s+|\s+--\s+|\s*\(', text)[0].strip()

    return text


def _strip_google_operators(query: str) -> str:
    """Strip site:, after:, before:, intitle:, inurl: operators from a query."""
    q = re.sub(r'site:\S+', '', query)
    q = re.sub(r'(?:after|before):\d{4}-\d{2}-\d{2}', '', q)
    q = re.sub(r'-?(?:intitle|inurl):', '', q)
    q = re.sub(r'\s+', ' ', q).strip()
    return q


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
