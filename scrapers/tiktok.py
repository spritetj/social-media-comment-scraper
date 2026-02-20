"""
TikTok Comments Scraper (Web App Edition)
==========================================
Extracted/refactored scraper for use in the Streamlit web app.
Scrapes comments (and replies) from TikTok videos using multiple methods:
  1. Direct API via aiohttp
  2. Playwright + internal API (browser-based fetch)
  3. Playwright scroll intercept (last resort)

Returns list[dict] — does NOT write files.
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs

import aiohttp

from utils.common import AdaptiveDelay

# Optional Playwright import
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# Suppress Playwright debug logging
logging.getLogger("playwright").setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

COMMENTS_PER_PAGE = 50
REPLIES_PER_PAGE = 50
MAX_RETRIES = 3
DEFAULT_MAX_COMMENTS = 0
DEFAULT_MAX_REPLIES = 5

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

CSV_FIELDNAMES = [
    "comment_id", "video_id", "video_url", "video_caption", "text", "created_at",
    "create_time_unix", "like_count", "reply_count", "is_reply",
    "reply_to_comment_id", "language", "user_id", "username",
    "nickname", "avatar_url", "is_author_liked",
]


# ---------------------------------------------------------------------------
#  Module-level helpers
# ---------------------------------------------------------------------------

def extract_video_id(url: str) -> str:
    """
    Extract the video ID (aweme_id) from a TikTok URL.
    Supports formats like:
      https://www.tiktok.com/@user/video/1234567890
      https://vm.tiktok.com/abcdef/
      https://www.tiktok.com/t/abcdef/
    """
    match = re.search(r"/(?:video|photo)/(\d+)", url)
    if match:
        return match.group(1)

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "item_id" in qs:
        return qs["item_id"][0]

    return ""


def format_timestamp(ts) -> str:
    """Convert a Unix timestamp to a human-readable datetime string."""
    try:
        if isinstance(ts, (int, float)) and ts > 0:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return str(ts) if ts else ""


def parse_comment(raw: dict, video_id: str = "", video_url: str = "") -> dict:
    """
    Parse a raw TikTok comment JSON object into a clean, flat record.
    Matches the output format of Apify's TikTok Comments Scraper.
    """
    user = raw.get("user", {})

    comment_id = str(raw.get("cid", raw.get("id", "")))
    text = raw.get("text", raw.get("comment", ""))
    create_time = raw.get("create_time", 0)
    like_count = raw.get("digg_count", raw.get("like_count", 0))
    reply_count = raw.get("reply_comment_total", raw.get("reply_count", 0))
    is_author = raw.get("is_author_digged", 0)

    # User info
    user_id = str(user.get("uid", user.get("id", "")))
    unique_id = user.get("unique_id", user.get("uniqueId", ""))
    nickname = user.get("nickname", "")
    avatar = user.get("avatar_thumb", {})
    if isinstance(avatar, dict):
        avatar_url = ""
        url_list = avatar.get("url_list", [])
        if url_list:
            avatar_url = url_list[0]
    elif isinstance(avatar, str):
        avatar_url = avatar
    else:
        avatar_url = ""

    # Comment language
    language = raw.get("comment_language", "")

    # Reply info
    reply_to_id = str(raw.get("reply_id", "")) if raw.get("reply_id") else ""

    return {
        "comment_id": comment_id,
        "video_id": video_id,
        "video_url": video_url,
        "video_caption": "",
        "text": text,
        "created_at": format_timestamp(create_time),
        "create_time_unix": create_time,
        "like_count": like_count,
        "reply_count": reply_count,
        "is_reply": bool(reply_to_id and reply_to_id != "0"),
        "reply_to_comment_id": reply_to_id,
        "language": language,
        "user_id": user_id,
        "username": unique_id,
        "nickname": nickname,
        "avatar_url": avatar_url,
        "is_author_liked": bool(is_author),
    }


def _clean_error(e: Exception) -> str:
    """Strip verbose Playwright browser launch logs from error messages."""
    msg = str(e)
    idx = msg.find("Browser logs:")
    if idx != -1:
        msg = msg[:idx].strip()
    idx = msg.find("=== logs ===")
    if idx != -1:
        msg = msg[:idx].strip()
    lines = msg.split("\n")
    clean = [ln for ln in lines if not ln.strip().startswith("<launch") and "--disable-" not in ln]
    return "\n".join(clean).strip() or "Browser closed unexpectedly"


# ---------------------------------------------------------------------------
#  Core scraper class
# ---------------------------------------------------------------------------

class TikTokCommentScraper:
    """
    Scrapes comments from TikTok videos.

    Architecture (same as Apify's approach):
    1. Try direct API via aiohttp (fastest)
    2. Fall back to Playwright + in-page fetch (browser cookies)
    3. Last resort: Playwright scroll intercept (network interception)

    Returns list[dict] — no file I/O.
    """

    def __init__(
        self,
        headless: bool = True,
        max_comments: int = 0,
        max_replies: int = 5,
        progress_callback: callable = None,
    ):
        self.headless = headless
        self.max_comments = max_comments      # 0 = no limit
        self.max_replies = max_replies         # -1 = skip, 0 = all, N = limit
        self._progress_callback = progress_callback

    # -- Progress reporting -------------------------------------------------

    def _progress(self, message: str):
        """Send a progress message via the callback (if provided)."""
        if self._progress_callback:
            try:
                self._progress_callback(message)
            except Exception:
                pass

    # ======================================================================
    #  Method 1: Direct API via aiohttp (fastest, no browser needed)
    # ======================================================================

    async def _scrape_comments_api(
        self,
        video_url: str,
        video_id: str,
        deadline: float = 0,
    ) -> list[dict]:
        """
        Try calling TikTok's comment API directly via aiohttp.
        Uses async HTTP with connection pooling.
        """
        comments = []
        cursor = 0
        has_more = True
        comment_ids_seen = set()
        delay = AdaptiveDelay()

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": video_url,
            "Accept": "application/json",
        }

        self._progress("Fetching comments...")

        connector = aiohttp.TCPConnector(limit=10, keepalive_timeout=30)
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            while has_more:
                if deadline and time.monotonic() > deadline:
                    self._progress(
                        f"Per-video timeout reached ({len(comments)} comments collected)"
                    )
                    break

                params = {
                    "aweme_id": video_id,
                    "cursor": cursor,
                    "count": COMMENTS_PER_PAGE,
                    "aid": "1988",
                }
                api_url = f"https://www.tiktok.com/api/comment/list/?{urlencode(params)}"

                for attempt in range(MAX_RETRIES):
                    try:
                        async with session.get(
                            api_url, timeout=aiohttp.ClientTimeout(total=15)
                        ) as resp:
                            if resp.status == 429:
                                delay.on_rate_limit()
                                await delay.wait()
                                continue
                            if resp.status == 200:
                                data = await resp.json(content_type=None)
                                raw_comments = data.get("comments", [])
                                if raw_comments:
                                    for raw in raw_comments:
                                        c = parse_comment(raw, video_id, video_url)
                                        if c["comment_id"] not in comment_ids_seen:
                                            comment_ids_seen.add(c["comment_id"])
                                            comments.append(c)

                                has_more = data.get("has_more", 0) == 1
                                cursor = data.get("cursor", cursor + COMMENTS_PER_PAGE)
                                delay.on_success()

                                self._progress(f"  ... {len(comments)} comments fetched")
                                break
                            else:
                                delay.on_error()
                                if attempt == MAX_RETRIES - 1:
                                    has_more = False
                    except Exception:
                        delay.on_error()
                        if attempt == MAX_RETRIES - 1:
                            has_more = False
                        else:
                            await asyncio.sleep(1)

                # Check max limit
                if self.max_comments > 0 and len(comments) >= self.max_comments:
                    comments = comments[: self.max_comments]
                    break

                await delay.wait()

        # -- Fetch replies concurrently via aiohttp -------------------------
        if self.max_replies >= 0 and comments:
            reply_delay = AdaptiveDelay()
            replies = await self._fetch_replies_concurrent(
                comments, video_id, video_url, comment_ids_seen,
                headers, {}, reply_delay, deadline,
            )
            comments.extend(replies)

        return comments

    # ======================================================================
    #  Method 2: Playwright + internal API (browser session cookies)
    # ======================================================================

    async def _scrape_comments_playwright_api(
        self,
        video_url: str,
        video_id: str,
        deadline: float = 0,
    ) -> list[dict]:
        """
        Use Playwright to establish a valid browser session, then call
        the comment API from within the page context (bypasses CORS / anti-bot).
        """
        if not PLAYWRIGHT_AVAILABLE:
            return []

        comments = []
        comment_ids_seen = set()
        pw = None
        browser = None

        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=self.headless,
                handle_sigint=False,
                args=[
                    "--mute-audio",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = await context.new_page()

            # Block heavy media to save bandwidth
            await page.route(
                "**/*.{mp4,webm,ogg,mp3,wav,m4a,aac,m3u8,ts}",
                lambda route: route.abort(),
            )

            # Navigate to video to establish session cookies
            self._progress("Establishing session...")
            nav_ok = False
            try:
                await page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(4000)
                nav_ok = True
            except Exception:
                try:
                    await page.goto(video_url, wait_until="commit", timeout=30000)
                    await page.wait_for_timeout(3000)
                    nav_ok = True
                except Exception:
                    pass

            if not nav_ok:
                raise RuntimeError("Could not load TikTok page")

            # Use page.evaluate to call the API from within the page context
            self._progress("Fetching comments via internal API...")
            cursor = 0
            has_more = True
            page_num = 0
            consecutive_errors = 0
            delay = AdaptiveDelay()

            while has_more:
                if deadline and time.monotonic() > deadline:
                    self._progress(
                        f"Per-video timeout reached ({len(comments)} comments collected)"
                    )
                    break

                page_num += 1
                try:
                    api_result = await page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch(
                                    '/api/comment/list/?aweme_id={video_id}&cursor={cursor}&count={COMMENTS_PER_PAGE}&aid=1988',
                                    {{ credentials: 'include' }}
                                );
                                if (resp.ok) {{
                                    return await resp.json();
                                }}
                                return {{ error: resp.status }};
                            }} catch(e) {{
                                return {{ error: e.message }};
                            }}
                        }}
                    """)
                except Exception:
                    consecutive_errors += 1
                    delay.on_error()
                    if consecutive_errors >= 2:
                        break
                    await delay.wait()
                    continue

                if not api_result or "error" in api_result:
                    error_code = api_result.get("error") if api_result else None
                    if error_code == 429:
                        delay.on_rate_limit()
                        await delay.wait()
                        continue
                    consecutive_errors += 1
                    delay.on_error()
                    if consecutive_errors >= 2:
                        break
                    await delay.wait()
                    continue

                consecutive_errors = 0
                raw_comments = api_result.get("comments", [])
                if raw_comments:
                    for raw in raw_comments:
                        c = parse_comment(raw, video_id, video_url)
                        if c["comment_id"] not in comment_ids_seen:
                            comment_ids_seen.add(c["comment_id"])
                            comments.append(c)

                has_more = api_result.get("has_more", 0) == 1
                cursor = api_result.get("cursor", cursor + COMMENTS_PER_PAGE)
                delay.on_success()

                self._progress(f"  Page {page_num}: {len(comments)} comments total")

                # Check max limit
                if self.max_comments > 0 and len(comments) >= self.max_comments:
                    comments = comments[: self.max_comments]
                    has_more = False

                await delay.wait()

            # -- Fetch replies concurrently via aiohttp ---------------------
            if self.max_replies >= 0 and comments:
                browser_cookies = await context.cookies()
                cookies_dict = {c["name"]: c["value"] for c in browser_cookies}
                headers = {"User-Agent": USER_AGENT, "Referer": video_url}

                reply_delay = AdaptiveDelay()
                replies = await self._fetch_replies_concurrent(
                    comments, video_id, video_url, comment_ids_seen,
                    headers, cookies_dict, reply_delay, deadline,
                )
                comments.extend(replies)

        except Exception as e:
            self._progress(f"Playwright method unavailable: {_clean_error(e)}")
        finally:
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass
            try:
                if pw:
                    await pw.stop()
            except Exception:
                pass

        return comments

    # ======================================================================
    #  Method 3: Playwright scroll intercept (last resort)
    # ======================================================================

    async def _scrape_comments_playwright(
        self,
        video_url: str,
        video_id: str,
        deadline: float = 0,
    ) -> list[dict]:
        """
        Open the TikTok video, scroll to load comments, and intercept
        the /api/comment/list/ responses from the network.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return []

        comments = []
        comment_ids_seen = set()
        pw = None
        browser = None

        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=self.headless,
                handle_sigint=False,
                args=[
                    "--mute-audio",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = await context.new_page()

            # Block media to save bandwidth and prevent sound
            await page.route(
                "**/*.{mp4,webm,ogg,mp3,wav,m4a,aac,m3u8,ts}",
                lambda route: route.abort(),
            )

            # -- Intercept comment API responses ----------------------------
            async def handle_response(response):
                url_str = response.url
                if "/api/comment/list/" in url_str and "/reply/" not in url_str:
                    try:
                        data = await response.json()
                        raw_comments = data.get("comments", [])
                        if raw_comments:
                            for raw in raw_comments:
                                c = parse_comment(raw, video_id, video_url)
                                if c["comment_id"] not in comment_ids_seen:
                                    comment_ids_seen.add(c["comment_id"])
                                    comments.append(c)
                    except Exception:
                        pass

            page.on("response", handle_response)

            # -- Navigate to the video page ---------------------------------
            self._progress("Opening video page...")
            try:
                await page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(4000)
            except Exception:
                try:
                    await page.goto(video_url, wait_until="commit", timeout=30000)
                    await page.wait_for_timeout(3000)
                except Exception:
                    raise RuntimeError("Could not load TikTok page")

            # -- Scroll down to trigger comment loading ---------------------
            self._progress("Scrolling to load comments...")
            max_scroll = (
                50
                if self.max_comments == 0
                else (self.max_comments // COMMENTS_PER_PAGE) + 5
            )
            no_new_count = 0
            prev_count = 0

            for scroll_i in range(max_scroll):
                if deadline and time.monotonic() > deadline:
                    self._progress(
                        f"Per-video timeout reached ({len(comments)} comments collected)"
                    )
                    break

                try:
                    await page.evaluate("window.scrollBy(0, 800)")
                    await page.wait_for_timeout(1500)
                except Exception:
                    break

                current_count = len(comments)
                if current_count > prev_count:
                    no_new_count = 0
                    prev_count = current_count
                    self._progress(f"  ... {current_count} comments loaded")
                else:
                    no_new_count += 1

                if self.max_comments > 0 and current_count >= self.max_comments:
                    break

                if no_new_count >= 5:
                    self._progress(
                        f"  No more comments to load (total: {current_count})"
                    )
                    break

                # Try clicking "View more comments" button if present
                try:
                    more_btn = page.locator('p[data-e2e="view-more-1"]')
                    if await more_btn.count() > 0:
                        await more_btn.first.click()
                        await page.wait_for_timeout(2000)
                except Exception:
                    pass

        except Exception as e:
            self._progress(f"Scroll method unavailable: {_clean_error(e)}")
        finally:
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass
            try:
                if pw:
                    await pw.stop()
            except Exception:
                pass

        # Apply max limit
        if self.max_comments > 0:
            comments = comments[: self.max_comments]

        return comments

    # ======================================================================
    #  Reply fetching helpers
    # ======================================================================

    async def _fetch_replies_for_comment(
        self,
        session: aiohttp.ClientSession,
        comment: dict,
        video_id: str,
        video_url: str,
        comment_ids_seen: set,
        delay: AdaptiveDelay,
        deadline: float = 0,
    ) -> list[dict]:
        """Fetch all reply pages for a single comment using aiohttp."""
        replies = []
        reply_cursor = 0
        reply_has_more = True
        replies_collected = 0
        max_r = self.max_replies if self.max_replies > 0 else max(comment["reply_count"], 9999)

        while reply_has_more and replies_collected < max_r:
            if deadline and time.monotonic() > deadline:
                break

            reply_params = {
                "item_id": video_id,
                "comment_id": comment["comment_id"],
                "cursor": reply_cursor,
                "count": REPLIES_PER_PAGE,
                "aid": "1988",
            }
            reply_url = (
                f"https://www.tiktok.com/api/comment/list/reply/?{urlencode(reply_params)}"
            )

            for attempt in range(MAX_RETRIES):
                try:
                    async with session.get(
                        reply_url, timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status == 429:
                            delay.on_rate_limit()
                            await delay.wait()
                            continue
                        if resp.status == 200:
                            reply_data = await resp.json(content_type=None)
                            raw_replies = reply_data.get("comments", [])
                            if raw_replies:
                                for raw in raw_replies:
                                    r = parse_comment(raw, video_id, video_url)
                                    r["is_reply"] = True
                                    r["reply_to_comment_id"] = comment["comment_id"]
                                    if r["comment_id"] not in comment_ids_seen:
                                        comment_ids_seen.add(r["comment_id"])
                                        replies.append(r)
                                        replies_collected += 1
                            reply_has_more = reply_data.get("has_more", 0) == 1
                            reply_cursor = reply_data.get(
                                "cursor", reply_cursor + REPLIES_PER_PAGE
                            )
                            delay.on_success()
                            break
                        else:
                            delay.on_error()
                            if attempt == MAX_RETRIES - 1:
                                reply_has_more = False
                except Exception:
                    delay.on_error()
                    if attempt == MAX_RETRIES - 1:
                        reply_has_more = False
                    else:
                        await asyncio.sleep(0.5)

            await delay.wait()

        return replies

    async def _fetch_replies_concurrent(
        self,
        comments: list[dict],
        video_id: str,
        video_url: str,
        comment_ids_seen: set,
        headers: dict,
        cookies: dict,
        delay: AdaptiveDelay,
        deadline: float = 0,
        concurrency: int = 5,
    ) -> list[dict]:
        """Fetch replies for all comments concurrently with bounded parallelism."""
        comments_with_replies = [
            c for c in comments if c["reply_count"] > 0 and not c["is_reply"]
        ]
        if not comments_with_replies:
            return []

        self._progress(
            f"Fetching replies for {len(comments_with_replies)} comment(s) "
            f"({concurrency} concurrent)..."
        )
        all_replies = []
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_fetch(session, comment, idx):
            async with semaphore:
                result = await self._fetch_replies_for_comment(
                    session, comment, video_id, video_url,
                    comment_ids_seen, delay, deadline,
                )
                if (idx + 1) % 20 == 0 or idx + 1 == len(comments_with_replies):
                    self._progress(
                        f"  ... replies fetched for {idx + 1}/"
                        f"{len(comments_with_replies)} comments"
                    )
                return result

        connector = aiohttp.TCPConnector(limit=concurrency + 2, keepalive_timeout=30)
        async with aiohttp.ClientSession(
            headers=headers, cookies=cookies, connector=connector
        ) as session:
            tasks = [
                bounded_fetch(session, c, i)
                for i, c in enumerate(comments_with_replies)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_replies.extend(result)
            elif isinstance(result, Exception):
                self._progress(f"Reply fetch error: {result}")

        return all_replies

    # ======================================================================
    #  URL resolution & caption fetching
    # ======================================================================

    async def _resolve_url(self, url: str) -> str:
        """Resolve short TikTok URLs (vm.tiktok.com) to full URLs."""
        if "vm.tiktok.com" in url or "/t/" in url:
            try:
                async with aiohttp.ClientSession(
                    headers={"User-Agent": USER_AGENT}
                ) as session:
                    async with session.head(
                        url,
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        final_url = str(resp.url)
                        if "/video/" in final_url or "/photo/" in final_url:
                            self._progress(f"Resolved short URL -> {final_url}")
                            return final_url
            except Exception:
                pass
        return url

    async def _fetch_video_caption(self, video_url: str) -> str:
        """Fetch video caption via TikTok's public oEmbed API.

        Calls https://www.tiktok.com/oembed?url={video_url} and extracts the
        `title` field which contains the video caption. No auth required.
        Returns "" on any failure -- never blocks scraping.
        """
        oembed_url = f"https://www.tiktok.com/oembed?url={video_url}"
        for attempt in range(MAX_RETRIES):
            try:
                async with aiohttp.ClientSession(
                    headers={"User-Agent": USER_AGENT}
                ) as session:
                    async with session.get(
                        oembed_url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            caption = data.get("title", "")
                            if caption:
                                display = caption[:80] + ("..." if len(caption) > 80 else "")
                                self._progress(f"Caption: {display}")
                            return caption
                        elif resp.status == 429:
                            wait = 2 ** (attempt + 1)
                            self._progress(f"oEmbed rate limited, retrying in {wait}s...")
                            await asyncio.sleep(wait)
                            continue
                        else:
                            self._progress(
                                f"oEmbed returned {resp.status}, skipping caption"
                            )
                            return ""
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(1)
                continue
        return ""

    # ======================================================================
    #  Public entry point (cascade: api -> playwright_api -> playwright scroll)
    # ======================================================================

    async def scrape_video_comments(
        self, video_url: str, deadline: float = 0
    ) -> list[dict]:
        """
        Main entry point: scrape all comments from a single TikTok video.
        Tries multiple methods in order of reliability.
        Returns list[dict].
        """
        # Clean URL
        if not video_url.startswith("http"):
            video_url = f"https://{video_url}"

        # Resolve short URLs (vm.tiktok.com, etc.)
        video_url = await self._resolve_url(video_url)

        # Extract video ID
        video_id = extract_video_id(video_url)
        if not video_id:
            self._progress(f"Could not extract video ID from: {video_url}")
            self._progress("URL must contain /video/NUMBERS or /photo/NUMBERS")
            return []

        self._progress(f"Video ID: {video_id}")
        self._progress(f"URL: {video_url}")
        limit_text = f"{self.max_comments}" if self.max_comments > 0 else "ALL"
        self._progress(f"Comment limit: {limit_text}")
        if deadline:
            remaining = max(0, int(deadline - time.monotonic()))
            self._progress(f"Timeout: {remaining}s remaining")

        # Fetch video caption via oEmbed
        caption = await self._fetch_video_caption(video_url)

        # Method 1: Direct API (fastest and most reliable)
        self._progress("Trying direct API...")
        comments = await self._scrape_comments_api(video_url, video_id, deadline=deadline)

        # Method 2: Playwright + internal API (if direct fails)
        if not comments and (not deadline or time.monotonic() < deadline):
            self._progress("Trying browser-based API...")
            comments = await self._scrape_comments_playwright_api(
                video_url, video_id, deadline=deadline
            )

        # Method 3: Playwright scroll intercept (last resort)
        if not comments and (not deadline or time.monotonic() < deadline):
            self._progress("Trying scroll-based approach...")
            comments = await self._scrape_comments_playwright(
                video_url, video_id, deadline=deadline
            )

        # Attach video caption to all comments
        for c in comments:
            c["video_caption"] = caption

        return comments
