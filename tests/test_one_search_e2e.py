#!/usr/bin/env python3
"""
End-to-end test for the One Search pipeline.

Runs: query building → SERP search → comment scraping → normalization → analysis
Uses local test credentials (cookies, API key) — never pushes to git.

Usage:
    python tests/test_one_search_e2e.py
    python tests/test_one_search_e2e.py --topic "Yoguruto"
    python tests/test_one_search_e2e.py --platforms youtube tiktok
    python tests/test_one_search_e2e.py --max-urls 5 --max-comments 30
"""

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

# Project root
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


def load_serper_key() -> str:
    """Load Serper API key from SERP/API.md."""
    api_file = BASE / "SERP" / "API.md"
    if not api_file.exists():
        print("[ERROR] SERP/API.md not found — cannot run SERP searches")
        sys.exit(1)
    key = api_file.read_text().strip()
    print(f"[OK] Serper API key loaded ({key[:8]}...)")
    return key


def load_cookies(platform: str, filename: str) -> list[dict]:
    """Load cookies from local test credential file."""
    cookie_file = BASE / "SERP" / "Local_Test_Credential_DO_NOT_UPLOAD" / filename
    if not cookie_file.exists():
        print(f"[WARN] {filename} not found — {platform} may not work")
        return []

    from utils.common import load_cookies_as_list

    domain = "facebook.com" if platform == "facebook" else "instagram.com"
    cookies = load_cookies_as_list(cookie_file.read_text(), domain)
    print(f"[OK] {platform.title()} cookies loaded: {len(cookies)} entries")
    return cookies


def progress(msg: str):
    """Print timestamped progress."""
    elapsed = time.time() - _start_time
    print(f"  [{elapsed:6.1f}s] {msg}")


_start_time = time.time()


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="One Search E2E Test")
    parser.add_argument("--topic", default="Sushi pop ในไทย", help="Search topic")
    parser.add_argument("--platforms", nargs="+",
                        default=["youtube", "tiktok", "facebook", "instagram"],
                        help="Platforms to search")
    parser.add_argument("--max-urls", type=int, default=10, help="Max URLs per platform")
    parser.add_argument("--max-comments", type=int, default=50, help="Max comments per URL")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Stop after URL discovery (no comment scraping)")
    parser.add_argument("--llm-key", default="",
                        help="Anthropic/OpenAI/Gemini API key for LLM decomposition")
    parser.add_argument("--llm-provider", default="claude",
                        choices=["claude", "openai", "gemini"],
                        help="LLM provider to use (default: claude)")
    args = parser.parse_args()

    global _start_time
    _start_time = time.time()

    print_section(f"One Search E2E Test: \"{args.topic}\"")
    print(f"Platforms: {', '.join(args.platforms)}")
    print(f"Max URLs/platform: {args.max_urls}, Max comments/URL: {args.max_comments}")

    # --- Configure LLM if key provided ---
    if args.llm_key:
        env_map = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GOOGLE_API_KEY"}
        os.environ[env_map[args.llm_provider]] = args.llm_key
        print(f"[OK] LLM enabled: {args.llm_provider}")

    # --- Load credentials ---
    print_section("Step 0: Load Credentials")
    serper_key = load_serper_key()
    os.environ["SERPER_API_KEY"] = serper_key

    cookies_map = {}
    if "facebook" in args.platforms:
        fb_cookies = load_cookies("facebook", "fb_cookies.txt")
        if fb_cookies:
            cookies_map["facebook"] = fb_cookies
    if "instagram" in args.platforms:
        ig_cookies = load_cookies("instagram", "ig_cookies.txt")
        if ig_cookies:
            cookies_map["instagram"] = ig_cookies

    # --- Step 1: Query building ---
    print_section("Step 1: Build Search Queries")
    relevance_keywords = None
    try:
        from search.intelligent_query_builder import build_intelligent_queries
        from utils.async_runner import run_async

        iq_result = run_async(build_intelligent_queries(
            user_input=args.topic,
            platforms=args.platforms,
            progress_callback=progress,
        ))

        # IntelligentQueryResult has .queries and .relevance_keywords
        queries = iq_result.queries
        relevance_keywords = iq_result.relevance_keywords

        total_queries = 0
        for platform, q_list in queries.items():
            total_queries += len(q_list)
            print(f"\n  {platform.upper()}: {len(q_list)} queries")
            for i, q in enumerate(q_list[:3]):
                print(f"    [{i+1}] {q}")
            if len(q_list) > 3:
                print(f"    ... and {len(q_list)-3} more")

        print(f"\n  TOTAL: {total_queries} queries across {len(queries)} platforms")
        if relevance_keywords:
            print(f"  Relevance keywords: {relevance_keywords}")
    except Exception as e:
        print(f"[ERROR] Query building failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    # --- Step 2: SERP search ---
    print_section("Step 2: SERP URL Discovery")
    try:
        from search.google_search import search_multi_queries
        from search.query_builder import extract_urls_from_results

        search_results = search_multi_queries(
            queries,
            max_results_per_query=args.max_urls,
            progress_callback=progress,
            topic=args.topic,
            relevance_keywords=relevance_keywords,
        )

        url_map = {}
        for platform in args.platforms:
            platform_results = search_results.get(platform, [])
            urls = extract_urls_from_results(platform_results, platform)
            if not urls:
                urls = [r["url"] for r in platform_results if r.get("url", "").startswith("http")]
            url_map[platform] = urls[:args.max_urls]

        print(f"\n  URL Discovery Summary:")
        total_urls = 0
        for platform, urls in url_map.items():
            total_urls += len(urls)
            print(f"    {platform.upper()}: {len(urls)} URLs")
            for u in urls[:3]:
                print(f"      - {u[:80]}")
            if len(urls) > 3:
                print(f"      ... and {len(urls)-3} more")

        print(f"\n  TOTAL: {total_urls} URLs across {len(url_map)} platforms")

        if total_urls == 0:
            print("\n[ERROR] No URLs found — check Serper API key and query format")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] SERP search failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    if args.skip_scrape:
        print_section("Skipping scraping (--skip-scrape)")
        print(f"\nDone in {time.time() - _start_time:.1f}s")
        return

    # --- Step 3: Comment scraping ---
    print_section("Step 3: Comment Scraping")
    try:
        from search.orchestrator import scrape_all_platforms

        raw_comments = run_async(scrape_all_platforms(
            url_map=url_map,
            cookies_map=cookies_map,
            progress_callback=progress,
            max_comments_per_url=args.max_comments,
        ))

        print(f"\n  Scraping Summary:")
        total_comments = 0
        for platform in args.platforms:
            comments = raw_comments.get(platform, [])
            total_comments += len(comments)
            print(f"    {platform.upper()}: {len(comments)} comments")
            if comments:
                sample = comments[0]
                text = sample.get("text", "")[:100]
                user = sample.get("profileName") or sample.get("username") or sample.get("ownerUsername", "?")
                print(f"      Sample: [{user}] {text}")

        print(f"\n  TOTAL: {total_comments} raw comments")
    except Exception as e:
        print(f"[ERROR] Comment scraping failed: {e}")
        traceback.print_exc()
        raw_comments = {}
        total_comments = 0

    # --- Step 4: Normalization ---
    print_section("Step 4: Comment Normalization")
    try:
        from utils.schema import normalize_comments

        all_clean = []
        for platform, comments in raw_comments.items():
            if comments:
                normalized = normalize_comments(comments, platform)
                all_clean.extend(normalized)
                print(f"  {platform.upper()}: {len(normalized)} normalized")

        print(f"\n  TOTAL: {len(all_clean)} clean comments")

        if all_clean:
            sample = all_clean[0]
            print(f"  Sample normalized comment:")
            for key in ["platform", "text", "username", "likes", "replies", "date"]:
                val = sample.get(key, "")
                if key == "text" and len(str(val)) > 80:
                    val = str(val)[:80] + "..."
                print(f"    {key}: {val}")
    except Exception as e:
        print(f"[ERROR] Normalization failed: {e}")
        traceback.print_exc()
        all_clean = []

    # --- Step 5: Analysis ---
    print_section("Step 5: Analysis")
    if len(all_clean) < 10:
        print(f"  Skipping — need >= 10 comments, got {len(all_clean)}")
    else:
        try:
            from analysis.pipeline import run_full_analysis

            analysis = run_full_analysis(all_clean)

            print(f"  Comment count: {analysis.get('comment_count', 0)}")

            if analysis.get("errors"):
                print(f"  Errors: {analysis['errors']}")

            if analysis.get("sentiment"):
                sent = analysis["sentiment"]
                print(f"  Sentiment: {sent}")

            if analysis.get("keywords"):
                kw = analysis["keywords"]
                if isinstance(kw, dict) and "top_keywords" in kw:
                    top = kw["top_keywords"][:5]
                    print(f"  Top keywords: {top}")
                else:
                    print(f"  Keywords: {str(kw)[:200]}")

            if analysis.get("topics"):
                print(f"  Topics: {str(analysis['topics'])[:200]}")

            if analysis.get("engagement"):
                print(f"  Engagement: {str(analysis['engagement'])[:200]}")

            if analysis.get("temporal"):
                print(f"  Temporal: {str(analysis['temporal'])[:200]}")

        except Exception as e:
            print(f"[ERROR] Analysis failed: {e}")
            traceback.print_exc()

    # --- Summary ---
    print_section("SUMMARY")
    elapsed = time.time() - _start_time
    print(f"  Topic: {args.topic}")
    print(f"  Platforms: {', '.join(args.platforms)}")
    print(f"  Queries generated: {sum(len(v) for v in queries.values())}")
    print(f"  URLs discovered: {sum(len(v) for v in url_map.values())}")
    print(f"  Comments scraped: {total_comments}")
    print(f"  Comments normalized: {len(all_clean)}")
    print(f"  Analysis ran: {'Yes' if len(all_clean) >= 10 else 'No (< 10 comments)'}")
    print(f"  Time elapsed: {elapsed:.1f}s")
    print()


if __name__ == "__main__":
    main()
