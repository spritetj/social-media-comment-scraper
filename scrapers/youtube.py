"""
YouTube Comments Scraper (Web Edition)
=======================================
Extracted/refactored YouTube comment scraper for use in the Streamlit web app.
No file I/O, no Rich console, no interactive menu — returns list[dict] only.

Uses YouTube's InnerTube API with a 3-method cascade:
  Method 1: Direct InnerTube API via aiohttp (fastest, no browser needed)
  Method 2: yt-dlp Python API (fallback if InnerTube blocked)
  Method 3: Playwright + InnerTube (last resort, browser session bypasses IP blocks)
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import aiohttp
import requests

from utils.common import AdaptiveDelay, _parse_count_string

# Optional: Playwright (only for Method 3)
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# Optional: yt-dlp (for Method 2)
YTDLP_AVAILABLE = False
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    pass

# Suppress noisy logging
logging.getLogger("playwright").setLevel(logging.ERROR)
logging.getLogger("yt_dlp").setLevel(logging.ERROR)


def _clean_error(e: Exception) -> str:
    """Strip verbose browser launch logs from error messages."""
    msg = str(e)
    for marker in ("Browser logs:", "=== logs ==="):
        idx = msg.find(marker)
        if idx != -1:
            msg = msg[:idx].strip()
    lines = msg.split("\n")
    clean = [l for l in lines if not l.strip().startswith("<launch") and "--disable-" not in l]
    return "\n".join(clean).strip() or "Unexpected error"


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1/next"
INNERTUBE_CLIENT = {
    "clientName": "WEB",
    "clientVersion": "2.20250101.00.00",
    "hl": "en",
    "gl": "US",
}
INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"

COMMENTS_PER_PAGE = 20
MAX_RETRIES = 3
DEFAULT_MAX_COMMENTS = 0
DEFAULT_MAX_REPLIES = 5

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

CSV_FIELDNAMES = [
    "id", "youtubeUrl", "videoTitle", "commentUrl", "date", "text",
    "profileName", "profileId", "profilePicture", "profileUrl",
    "likesCount", "commentsCount", "threadingDepth",
    "isPinned", "isOwner", "isVerified", "inputUrl",
]


# ---------------------------------------------------------------------------
#  URL helpers  (module-level, exported)
# ---------------------------------------------------------------------------

def extract_video_id(url: str) -> str:
    """
    Extract the video ID from a YouTube URL.
    Supports formats:
      https://www.youtube.com/watch?v=VIDEO_ID
      https://youtu.be/VIDEO_ID
      https://www.youtube.com/shorts/VIDEO_ID
      https://www.youtube.com/embed/VIDEO_ID
      https://www.youtube.com/live/VIDEO_ID
      https://www.youtube.com/v/VIDEO_ID
      https://m.youtube.com/watch?v=VIDEO_ID
    """
    if not url:
        return ""

    url = url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    parsed = urlparse(url)

    # youtu.be/VIDEO_ID
    if parsed.hostname in ("youtu.be",):
        vid = parsed.path.lstrip("/").split("/")[0]
        if vid:
            return vid.split("?")[0]

    # youtube.com/watch?v=VIDEO_ID
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]

    # youtube.com/shorts/VIDEO_ID or /embed/VIDEO_ID or /live/VIDEO_ID or /v/VIDEO_ID
    match = re.search(r"/(?:shorts|embed|live|v)/([a-zA-Z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    # Last resort: look for 11-char ID pattern in path
    match = re.search(r"([a-zA-Z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    return ""


def normalize_youtube_url(url: str) -> str:
    """Normalize a YouTube URL to standard watch?v= format."""
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


# ---------------------------------------------------------------------------
#  InnerTube API core
# ---------------------------------------------------------------------------

def _build_innertube_body(continuation: str) -> dict:
    """Build the request body for InnerTube /next API calls."""
    return {
        "context": {
            "client": INNERTUBE_CLIENT,
        },
        "continuation": continuation,
    }


async def fetch_initial_data(
    video_url: str,
    session: aiohttp.ClientSession,
    progress_fn=None,
) -> dict | None:
    """GET the YouTube watch page and extract ytInitialData JSON blob."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }

    _progress = progress_fn or (lambda m: None)

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(
                video_url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue
                html = await resp.text()

                # Extract ytInitialData JSON blob
                match = re.search(
                    r'var\s+ytInitialData\s*=\s*(\{.+?\});\s*</script>',
                    html, re.DOTALL,
                )
                if not match:
                    match = re.search(
                        r'window\["ytInitialData"\]\s*=\s*(\{.+?\});\s*',
                        html, re.DOTALL,
                    )
                if not match:
                    match = re.search(
                        r"ytInitialData\s*=\s*'(\{.+?\})'",
                        html, re.DOTALL,
                    )

                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        _progress("Could not load video")
                        return None
                else:
                    _progress("Could not load video data")
                    return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                _progress("Could not load video")
    return None


def find_comments_continuation(initial_data: dict) -> str | None:
    """Navigate ytInitialData JSON to find the comments continuation token.

    Path: contents.twoColumnWatchNextResults.results.results.contents[]
      -> find itemSectionRenderer with sectionIdentifier == "comment-item-section"
      -> continuations[0].nextContinuationData.continuation
    """
    try:
        contents = (
            initial_data
            .get("contents", {})
            .get("twoColumnWatchNextResults", {})
            .get("results", {})
            .get("results", {})
            .get("contents", [])
        )

        for item in contents:
            section = item.get("itemSectionRenderer", {})
            if section.get("sectionIdentifier") == "comment-item-section":
                continuations = section.get("continuations", [])
                if continuations:
                    cont_data = continuations[0].get("nextContinuationData", {})
                    token = cont_data.get("continuation")
                    if token:
                        return token

            section_contents = section.get("contents", [])
            for sc in section_contents:
                cont_renderer = sc.get("continuationItemRenderer", {})
                cont_endpoint = cont_renderer.get("continuationEndpoint", {})
                cont_command = cont_endpoint.get("continuationCommand", {})
                token = cont_command.get("token")
                if token:
                    return token

    except Exception:
        pass

    # Recursive fallback
    return _find_continuation_recursive(initial_data)


def _find_continuation_recursive(obj, depth=0) -> str | None:
    """Recursively search JSON for a comments continuation token."""
    if depth > 15:
        return None

    if isinstance(obj, dict):
        if "continuationCommand" in obj:
            cmd = obj["continuationCommand"]
            token = cmd.get("token", "")
            if token and len(token) > 50:
                return token

        if "nextContinuationData" in obj:
            token = obj["nextContinuationData"].get("continuation", "")
            if token and len(token) > 50:
                return token

        if obj.get("sectionIdentifier") == "comment-item-section":
            for key, value in obj.items():
                result = _find_continuation_recursive(value, depth + 1)
                if result:
                    return result

        for key, value in obj.items():
            if key in (
                "comments", "continuation", "continuations", "contents",
                "itemSectionRenderer", "continuationItemRenderer",
                "continuationEndpoint", "continuationCommand",
                "nextContinuationData", "twoColumnWatchNextResults",
                "results", "sectionListRenderer",
            ):
                result = _find_continuation_recursive(value, depth + 1)
                if result:
                    return result

    elif isinstance(obj, list):
        for item in obj:
            result = _find_continuation_recursive(item, depth + 1)
            if result:
                return result

    return None


def extract_video_title(initial_data: dict) -> str:
    """Extract video title from ytInitialData."""
    try:
        contents = (
            initial_data
            .get("contents", {})
            .get("twoColumnWatchNextResults", {})
            .get("results", {})
            .get("results", {})
            .get("contents", [])
        )
        for item in contents:
            primary = item.get("videoPrimaryInfoRenderer", {})
            title = primary.get("title", {})
            runs = title.get("runs", [])
            if runs:
                return "".join(r.get("text", "") for r in runs)
    except Exception:
        pass

    try:
        return initial_data.get("videoDetails", {}).get("title", "")
    except Exception:
        pass

    return ""


async def fetch_comments_page(
    continuation: str,
    session: aiohttp.ClientSession,
    cookies: dict | None = None,
) -> dict | None:
    """POST to InnerTube /next API with continuation token to get a page of comments."""
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "X-YouTube-Client-Name": "1",
        "X-YouTube-Client-Version": INNERTUBE_CLIENT["clientVersion"],
    }

    body = _build_innertube_body(continuation)
    url = f"{INNERTUBE_API_URL}?key={INNERTUBE_API_KEY}"

    try:
        async with session.post(
            url, json=body, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
            elif resp.status == 429:
                return {"_rate_limited": True}
            else:
                return None
    except Exception:
        return None


def parse_comments_response(
    data: dict,
) -> tuple[list[dict], str | None, list[tuple[str, str]]]:
    """Parse InnerTube /next response.

    YouTube uses two formats:
    1. Legacy: commentRenderer inside commentThreadRenderer (older API versions)
    2. Modern: commentViewModel in threads + commentEntityPayload in frameworkUpdates

    Returns:
        (comments_parsed, next_continuation, reply_continuations)
        where reply_continuations is a list of (comment_id, continuation_token) tuples
    """
    comments_parsed = []
    next_continuation = None
    reply_continuations = []

    if not data:
        return comments_parsed, next_continuation, reply_continuations

    # Build a lookup of comment entities from frameworkUpdates (modern format)
    entity_map = {}
    framework_updates = data.get("frameworkUpdates", {})
    entity_batch = framework_updates.get("entityBatchUpdate", {})
    mutations = entity_batch.get("mutations", [])

    for mutation in mutations:
        payload = mutation.get("payload", {})
        entity = payload.get("commentEntityPayload", {})
        if entity:
            props = entity.get("properties", {})
            comment_id = props.get("commentId", "")
            if comment_id:
                entity_map[comment_id] = entity

    # Process onResponseReceivedEndpoints for thread structure + continuations
    endpoints = data.get("onResponseReceivedEndpoints", [])

    for endpoint in endpoints:
        actions = (
            endpoint.get("appendContinuationItemsAction", {}).get("continuationItems", [])
            or endpoint.get("reloadContinuationItemsCommand", {}).get("continuationItems", [])
        )

        for item in actions:
            # Comment thread
            thread = item.get("commentThreadRenderer", {})
            if thread:
                # Modern format: commentViewModel
                cvm_wrapper = thread.get("commentViewModel", {})
                cvm = cvm_wrapper.get("commentViewModel", {})
                if cvm:
                    comment_id = cvm.get("commentId", "")
                    if comment_id and comment_id in entity_map:
                        entity = entity_map[comment_id]
                        pinned_text = cvm.get("pinnedText", "")
                        if pinned_text:
                            entity.setdefault("properties", {})["pinnedText"] = pinned_text
                        comments_parsed.append(entity)

                # Legacy format: comment.commentRenderer
                comment_data = thread.get("comment", {}).get("commentRenderer", {})
                if comment_data and comment_data.get("commentId"):
                    cid = comment_data.get("commentId", "")
                    if cid not in entity_map:
                        comments_parsed.append(comment_data)

                # Reply continuation token
                replies_renderer = thread.get("replies", {}).get("commentRepliesRenderer", {})
                reply_conts = replies_renderer.get("contents", [])
                for rc in reply_conts:
                    cont_item_r = rc.get("continuationItemRenderer", {})
                    cont_endpoint = cont_item_r.get("continuationEndpoint", {})
                    cont_command = cont_endpoint.get("continuationCommand", {})
                    reply_token = cont_command.get("token", "")
                    if reply_token:
                        cid = ""
                        if cvm:
                            cid = cvm.get("commentId", "")
                        if not cid and comment_data:
                            cid = comment_data.get("commentId", "")
                        reply_continuations.append((cid, reply_token))
                        break

                # Alternative: button-based reply continuation
                if not reply_conts and replies_renderer:
                    button = replies_renderer.get("viewReplies", {}).get("buttonRenderer", {})
                    btn_command = button.get("command", {}).get("continuationCommand", {})
                    reply_token = btn_command.get("token", "")
                    if reply_token:
                        cid = cvm.get("commentId", "") if cvm else comment_data.get("commentId", "")
                        reply_continuations.append((cid, reply_token))

            # Standalone comment (in reply threads) -- modern format
            comment_vm = item.get("commentViewModel", {})
            if comment_vm:
                cid = comment_vm.get("commentId", "")
                if cid and cid in entity_map:
                    comments_parsed.append(entity_map[cid])

            # Standalone comment -- legacy format
            comment_renderer = item.get("commentRenderer", {})
            if comment_renderer and comment_renderer.get("commentId"):
                cid = comment_renderer["commentId"]
                if cid not in entity_map:
                    comments_parsed.append(comment_renderer)

            # Next page continuation
            cont_item = item.get("continuationItemRenderer", {})
            if cont_item:
                cont_endpoint = cont_item.get("continuationEndpoint", {})
                cont_command = cont_endpoint.get("continuationCommand", {})
                token = cont_command.get("token", "")
                if token:
                    next_continuation = token
                btn = cont_item.get("button", {}).get("buttonRenderer", {})
                btn_command = btn.get("command", {}).get("continuationCommand", {})
                btn_token = btn_command.get("token", "")
                if btn_token and not next_continuation:
                    next_continuation = btn_token

    # If we found entities but no threads matched (edge case), return all entities
    if not comments_parsed and entity_map:
        comments_parsed = list(entity_map.values())

    return comments_parsed, next_continuation, reply_continuations


# ---------------------------------------------------------------------------
#  Comment parser
# ---------------------------------------------------------------------------

def parse_comment(
    raw: dict,
    video_id: str = "",
    video_url: str = "",
    video_title: str = "",
    input_url: str = "",
    threading_depth: int = 0,
) -> dict:
    """Parse a YouTube comment into a clean, flat record.

    Handles two formats:
    1. Modern commentEntityPayload (from frameworkUpdates)
    2. Legacy commentRenderer (older API)
    """
    if "properties" in raw and "author" in raw:
        return _parse_entity_payload(raw, video_id, video_url, video_title, input_url, threading_depth)
    else:
        return _parse_comment_renderer(raw, video_id, video_url, video_title, input_url, threading_depth)


def _parse_entity_payload(
    entity: dict,
    video_id: str, video_url: str, video_title: str, input_url: str,
    threading_depth: int,
) -> dict:
    """Parse modern commentEntityPayload format."""
    props = entity.get("properties", {})
    author = entity.get("author", {})
    toolbar = entity.get("toolbar", {})
    avatar = entity.get("avatar", {})

    comment_id = props.get("commentId", "")
    text = props.get("content", {}).get("content", "")
    date = props.get("publishedTime", "")

    profile_name = author.get("displayName", "")
    profile_id = author.get("channelId", "")
    is_verified = author.get("isVerified", False)
    is_owner = author.get("isCreator", False)

    # Profile picture from avatar
    profile_picture = ""
    avatar_image = avatar.get("image", {})
    sources = avatar_image.get("sources", [])
    if sources:
        profile_picture = sources[-1].get("url", "")
    if not profile_picture:
        profile_picture = author.get("avatarThumbnailUrl", "")
    if profile_picture and profile_picture.startswith("//"):
        profile_picture = f"https:{profile_picture}"

    profile_url = f"https://www.youtube.com/channel/{profile_id}" if profile_id else ""

    # Like count from toolbar
    likes_text = toolbar.get("likeCountNotliked", toolbar.get("likeCountLiked", ""))
    likes_count = _parse_count_string(likes_text)

    # Reply count from toolbar
    reply_text = toolbar.get("replyCount", "0")
    comments_count = _parse_count_string(str(reply_text))

    # Pinned detection
    is_pinned = bool(props.get("pinnedText") or entity.get("pinnedText"))

    # Detect threading depth from properties
    reply_level = props.get("replyLevel", threading_depth)

    comment_url = (
        f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"
        if video_id and comment_id else ""
    )

    return {
        "id": comment_id,
        "youtubeUrl": video_url,
        "videoTitle": video_title,
        "commentUrl": comment_url,
        "date": date,
        "text": text,
        "profileName": profile_name,
        "profileId": profile_id,
        "profilePicture": profile_picture,
        "profileUrl": profile_url,
        "likesCount": likes_count,
        "commentsCount": comments_count,
        "threadingDepth": reply_level,
        "isPinned": is_pinned,
        "isOwner": is_owner,
        "isVerified": is_verified,
        "inputUrl": input_url,
    }


def _parse_comment_renderer(
    raw: dict,
    video_id: str, video_url: str, video_title: str, input_url: str,
    threading_depth: int,
) -> dict:
    """Parse legacy commentRenderer format."""
    comment_id = raw.get("commentId", "")

    # Comment text
    text_parts = []
    content_text = raw.get("contentText", {})
    runs = content_text.get("runs", [])
    if runs:
        for run in runs:
            text_parts.append(run.get("text", ""))
    elif isinstance(content_text, dict) and "simpleText" in content_text:
        text_parts.append(content_text["simpleText"])
    text = "".join(text_parts)

    # Author info
    author_text = raw.get("authorText", {})
    profile_name = author_text.get("simpleText", "")
    if not profile_name:
        author_runs = author_text.get("runs", [])
        if author_runs:
            profile_name = author_runs[0].get("text", "")

    author_endpoint = raw.get("authorEndpoint", {})
    browse_endpoint = author_endpoint.get("browseEndpoint", {})
    profile_id = browse_endpoint.get("browseId", "")

    author_thumb = raw.get("authorThumbnail", {})
    thumbnails = author_thumb.get("thumbnails", [])
    profile_picture = thumbnails[-1].get("url", "") if thumbnails else ""
    if profile_picture and profile_picture.startswith("//"):
        profile_picture = f"https:{profile_picture}"

    profile_url = f"https://www.youtube.com/channel/{profile_id}" if profile_id else ""

    vote_count = raw.get("voteCount", {})
    likes_text = (
        vote_count.get("simpleText", "") if isinstance(vote_count, dict) else str(vote_count)
    )
    likes_count = _parse_count_string(likes_text)

    reply_count_raw = raw.get("replyCount", 0)
    if isinstance(reply_count_raw, dict):
        reply_count_raw = 0
    comments_count = int(reply_count_raw) if reply_count_raw else 0

    published_time = raw.get("publishedTimeText", {})
    date = ""
    if isinstance(published_time, dict):
        if "runs" in published_time:
            date = published_time.get("runs", [{}])[0].get("text", "")
        else:
            date = published_time.get("simpleText", "")

    is_pinned = bool(raw.get("pinnedCommentBadge"))
    is_owner = bool(raw.get("authorIsChannelOwner"))
    author_badges = raw.get("authorCommentBadge", {})
    is_verified = bool(author_badges)

    comment_url = (
        f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"
        if video_id and comment_id else ""
    )

    return {
        "id": comment_id,
        "youtubeUrl": video_url,
        "videoTitle": video_title,
        "commentUrl": comment_url,
        "date": date,
        "text": text,
        "profileName": profile_name,
        "profileId": profile_id,
        "profilePicture": profile_picture,
        "profileUrl": profile_url,
        "likesCount": likes_count,
        "commentsCount": comments_count,
        "threadingDepth": threading_depth,
        "isPinned": is_pinned,
        "isOwner": is_owner,
        "isVerified": is_verified,
        "inputUrl": input_url,
    }


# ---------------------------------------------------------------------------
#  Core scraper class
# ---------------------------------------------------------------------------

class YouTubeCommentScraper:
    """
    Scrapes comments from YouTube videos using a 3-method cascade:
      Method 1: Direct InnerTube API via aiohttp (fastest)
      Method 2: yt-dlp Python API (fallback)
      Method 3: Playwright + InnerTube (last resort)

    Returns list[dict] -- does NOT write any files.
    """

    def __init__(
        self,
        headless: bool = True,
        max_comments: int = 0,
        max_replies: int = 5,
        sort_by: str = "top",
        progress_callback: callable = None,
    ):
        self.headless = headless
        self.max_comments = max_comments
        self.max_replies = max_replies
        self.sort_by = sort_by  # "top" or "newest"
        self._cookies = {}
        self._progress_callback = progress_callback

    # -- Progress helper ----------------------------------------------------

    def _progress(self, msg: str):
        """Send a progress message through the callback if one is set."""
        if self._progress_callback:
            try:
                self._progress_callback(msg)
            except Exception:
                pass

    # -- Cookie setter ------------------------------------------------------

    def set_cookies(self, cookies: dict):
        """Set cookies for authenticated requests."""
        self._cookies = cookies

    # -----------------------------------------------------------------------
    #  Method 1: Direct InnerTube API
    # -----------------------------------------------------------------------

    async def _scrape_comments_innertube(
        self,
        video_url: str,
        video_id: str,
        input_url: str = "",
        deadline: float = 0,
    ) -> list[dict]:
        """Primary method: scrape comments via direct InnerTube API calls."""
        comments = []
        comment_ids_seen = set()
        reply_continuations_all = []

        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }

        delay = AdaptiveDelay(min_delay=0.3, max_delay=10.0, initial=1.5)

        connector = aiohttp.TCPConnector(limit=10, keepalive_timeout=30)
        cookie_jar = aiohttp.CookieJar()
        async with aiohttp.ClientSession(
            headers=headers, connector=connector, cookie_jar=cookie_jar,
        ) as session:
            # Set cookies if available
            if self._cookies:
                for name, value in self._cookies.items():
                    cookie_jar.update_cookies(
                        {name: value},
                        response_url=aiohttp.client.URL("https://www.youtube.com"),
                    )

            # Step 1: Fetch initial page data
            self._progress("Loading video...")
            initial_data = await fetch_initial_data(
                video_url, session, progress_fn=self._progress,
            )
            if not initial_data:
                self._progress("Could not load video")
                return []

            # Extract video title
            video_title = extract_video_title(initial_data)
            if video_title:
                truncated = video_title[:80] + ("..." if len(video_title) > 80 else "")
                self._progress(f"Title: {truncated}")

            # Step 2: Find comments continuation token
            continuation = find_comments_continuation(initial_data)
            if not continuation:
                self._progress("No comments section found (comments may be disabled)")
                return []

            # Step 3: Pagination loop
            self._progress("Fetching comments...")
            page_num = 0
            consecutive_empty = 0
            last_cursor = None

            while continuation:
                if deadline and time.monotonic() > deadline:
                    self._progress(
                        f"Per-video timeout reached ({len(comments)} comments collected)"
                    )
                    break

                # Prevent infinite loops
                if continuation == last_cursor:
                    break
                last_cursor = continuation

                page_num += 1

                for attempt in range(MAX_RETRIES):
                    resp_data = await fetch_comments_page(
                        continuation, session, self._cookies,
                    )

                    if resp_data and resp_data.get("_rate_limited"):
                        delay.on_rate_limit()
                        self._progress("Please wait, loading...")
                        await delay.wait()
                        continue

                    if resp_data:
                        break
                    else:
                        delay.on_error()
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                else:
                    # All retries failed
                    break

                if not resp_data or resp_data.get("_rate_limited"):
                    break

                # Parse response
                raw_comments, next_continuation, reply_conts = parse_comments_response(
                    resp_data,
                )

                if not raw_comments:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                else:
                    consecutive_empty = 0

                # Process comments
                for raw in raw_comments:
                    c = parse_comment(
                        raw, video_id, video_url, video_title, input_url,
                        threading_depth=0,
                    )
                    if c["id"] and c["id"] not in comment_ids_seen:
                        comment_ids_seen.add(c["id"])
                        comments.append(c)

                # Collect reply continuation tokens
                reply_continuations_all.extend(reply_conts)

                continuation = next_continuation
                delay.on_success()

                self._progress(f"Found {len(comments)} comments so far...")

                # Check max limit
                if self.max_comments > 0 and len(comments) >= self.max_comments:
                    comments = comments[: self.max_comments]
                    break

                await delay.wait()

            # Step 4: Fetch replies
            if self.max_replies >= 0 and reply_continuations_all:
                replies = await self._fetch_replies_innertube(
                    session, reply_continuations_all, comment_ids_seen,
                    video_id, video_url, video_title, input_url, delay, deadline,
                )
                comments.extend(replies)

        return comments

    # -----------------------------------------------------------------------
    #  Reply fetcher (used by Methods 1 & 3)
    # -----------------------------------------------------------------------

    async def _fetch_replies_innertube(
        self,
        session: aiohttp.ClientSession,
        reply_continuations: list[tuple[str, str]],
        comment_ids_seen: set,
        video_id: str,
        video_url: str,
        video_title: str,
        input_url: str,
        delay: AdaptiveDelay,
        deadline: float = 0,
        concurrency: int = 3,
    ) -> list[dict]:
        """Fetch replies for comments using their continuation tokens."""
        if not reply_continuations:
            return []

        to_fetch = reply_continuations

        self._progress("Loading replies...")
        all_replies = []
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_one_comment_replies(
            parent_id: str, continuation: str, idx: int,
        ):
            async with semaphore:
                replies = []
                replies_collected = 0
                max_r = self.max_replies if self.max_replies > 0 else 9999
                current_cont = continuation

                while current_cont and replies_collected < max_r:
                    if deadline and time.monotonic() > deadline:
                        break

                    resp_data = await fetch_comments_page(
                        current_cont, session, self._cookies,
                    )

                    if not resp_data or resp_data.get("_rate_limited"):
                        if resp_data and resp_data.get("_rate_limited"):
                            delay.on_rate_limit()
                            await delay.wait()
                            resp_data = await fetch_comments_page(
                                current_cont, session, self._cookies,
                            )
                        if not resp_data or resp_data.get("_rate_limited"):
                            break

                    raw_replies, next_cont, _ = parse_comments_response(resp_data)

                    for raw in raw_replies:
                        r = parse_comment(
                            raw, video_id, video_url, video_title, input_url,
                            threading_depth=1,
                        )
                        if r["id"] and r["id"] not in comment_ids_seen:
                            comment_ids_seen.add(r["id"])
                            replies.append(r)
                            replies_collected += 1
                            if replies_collected >= max_r:
                                break

                    current_cont = next_cont
                    delay.on_success()
                    await delay.wait()

                if (idx + 1) % 10 == 0 or idx + 1 == len(to_fetch):
                    self._progress(f"Loading replies... ({idx + 1}/{len(to_fetch)})")

                return replies

        tasks = [
            fetch_one_comment_replies(parent_id, cont, i)
            for i, (parent_id, cont) in enumerate(to_fetch)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_replies.extend(result)
            elif isinstance(result, Exception):
                self._progress("Some replies could not be loaded")

        return all_replies

    # -----------------------------------------------------------------------
    #  Method 2: yt-dlp fallback
    # -----------------------------------------------------------------------

    async def _scrape_comments_ytdlp(
        self,
        video_url: str,
        video_id: str,
        input_url: str = "",
        deadline: float = 0,
    ) -> list[dict]:
        """Fallback: use yt-dlp to extract comments."""
        if not YTDLP_AVAILABLE:
            return []

        self._progress("Retrying...")

        loop = asyncio.get_event_loop()

        def _extract():
            sort_arg = "top" if self.sort_by == "top" else "new"
            max_comments_arg = (
                str(self.max_comments) if self.max_comments > 0 else "all"
            )

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "getcomments": True,
                "extractor_args": {
                    "youtube": {
                        "comment_sort": [sort_arg],
                        "max_comments": [
                            max_comments_arg, "all", "all",
                            str(max(self.max_replies, 0))
                            if self.max_replies >= 0 else "all",
                        ],
                    }
                },
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    return info
            except Exception as e:
                self._progress("Could not load comments")
                return None

        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, _extract),
                timeout=300,
            )
        except asyncio.TimeoutError:
            self._progress("Request timed out")
            return []

        if not info:
            return []

        video_title = info.get("title", "")
        raw_comments = info.get("comments", [])

        if not raw_comments:
            self._progress("No comments found")
            return []

        self._progress(f"Found {len(raw_comments)} comments")

        comments = []
        comment_ids_seen = set()
        video_url_normalized = normalize_youtube_url(video_url)

        for raw in raw_comments:
            c = self._parse_ytdlp_comment(
                raw, video_id, video_url_normalized, video_title, input_url,
            )
            if c["id"] and c["id"] not in comment_ids_seen:
                comment_ids_seen.add(c["id"])
                comments.append(c)

        if self.max_comments > 0:
            top_level = [c for c in comments if c["threadingDepth"] == 0]
            replies = [c for c in comments if c["threadingDepth"] > 0]
            top_level = top_level[: self.max_comments]
            top_ids = {c["id"] for c in top_level}
            filtered_replies = [
                r for r in replies
                if any(r["id"].startswith(tid) for tid in top_ids)
            ]
            comments = top_level + filtered_replies

        return comments

    def _parse_ytdlp_comment(
        self,
        raw: dict,
        video_id: str,
        video_url: str,
        video_title: str,
        input_url: str,
    ) -> dict:
        """Map yt-dlp comment format to our output format."""
        comment_id = raw.get("id", "")
        text = raw.get("text", "")
        author = raw.get("author", "")
        author_id = raw.get("author_id", "")
        author_thumbnail = raw.get("author_thumbnail", "")
        like_count = raw.get("like_count", 0) or 0
        is_pinned = raw.get("is_pinned", False)
        is_owner = raw.get("author_is_uploader", False)
        is_verified = raw.get("author_is_verified", False)

        # Threading
        parent = raw.get("parent", "root")
        threading_depth = 0 if parent == "root" else 1

        # Date
        timestamp = raw.get("timestamp")
        if timestamp:
            try:
                date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                date = raw.get("_time_text", "")
        else:
            date = raw.get("_time_text", "")

        # Reply count (only for top-level)
        reply_count = 0
        if threading_depth == 0:
            reply_count = raw.get("reply_count", 0) or 0

        comment_url = (
            f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"
            if comment_id else ""
        )
        profile_url = (
            f"https://www.youtube.com/channel/{author_id}" if author_id else ""
        )

        return {
            "id": comment_id,
            "youtubeUrl": video_url,
            "videoTitle": video_title,
            "commentUrl": comment_url,
            "date": date,
            "text": text,
            "profileName": author,
            "profileId": author_id,
            "profilePicture": author_thumbnail,
            "profileUrl": profile_url,
            "likesCount": like_count,
            "commentsCount": reply_count,
            "threadingDepth": threading_depth,
            "isPinned": is_pinned,
            "isOwner": is_owner,
            "isVerified": is_verified,
            "inputUrl": input_url,
        }

    # -----------------------------------------------------------------------
    #  Method 3: Playwright + InnerTube
    # -----------------------------------------------------------------------

    async def _scrape_comments_playwright(
        self,
        video_url: str,
        video_id: str,
        input_url: str = "",
        deadline: float = 0,
    ) -> list[dict]:
        """Last resort: use Playwright to load the page and call InnerTube from
        within the browser context."""
        if not PLAYWRIGHT_AVAILABLE:
            return []

        comments = []
        comment_ids_seen = set()
        reply_continuations_all = []
        video_title = ""
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

            # Add cookies if available
            if self._cookies:
                cookie_list = []
                for name, value in self._cookies.items():
                    cookie_list.append({
                        "name": name,
                        "value": value,
                        "domain": ".youtube.com",
                        "path": "/",
                    })
                if cookie_list:
                    await context.add_cookies(cookie_list)

            page = await context.new_page()

            # Block media to save bandwidth
            await page.route(
                "**/*.{mp4,webm,ogg,mp3,wav,m4a,aac,m3u8,ts}",
                lambda route: route.abort(),
            )

            # Navigate to the video page
            self._progress("Loading video...")
            try:
                await page.goto(
                    video_url, wait_until="domcontentloaded", timeout=45000,
                )
                await page.wait_for_timeout(4000)
            except Exception:
                try:
                    await page.goto(
                        video_url, wait_until="commit", timeout=30000,
                    )
                    await page.wait_for_timeout(3000)
                except Exception:
                    raise RuntimeError("Could not load YouTube page")

            # Extract ytInitialData from the browser
            try:
                initial_data = await page.evaluate("() => window.ytInitialData")
            except Exception:
                initial_data = None

            if initial_data:
                video_title = extract_video_title(initial_data)
                continuation = find_comments_continuation(initial_data)
            else:
                # Scroll down to trigger comment loading
                await page.evaluate("window.scrollBy(0, 500)")
                await page.wait_for_timeout(3000)

                try:
                    continuation = await page.evaluate("""
                        () => {
                            const scripts = document.querySelectorAll('script');
                            for (const script of scripts) {
                                const text = script.textContent;
                                if (text.includes('comment-item-section')) {
                                    const match = text.match(/"token":"([^"]+)"/);
                                    if (match) return match[1];
                                }
                            }
                            return null;
                        }
                    """)
                except Exception:
                    continuation = None

            if not continuation:
                self._progress("Could not load comments section")
                return []

            if video_title:
                truncated = video_title[:80] + ("..." if len(video_title) > 80 else "")
                self._progress(f"Title: {truncated}")

            # Use page.evaluate to call InnerTube API from within the browser
            self._progress("Fetching comments...")
            page_num = 0
            consecutive_empty = 0
            last_cursor = None
            delay = AdaptiveDelay(min_delay=0.5, max_delay=10.0, initial=2.0)

            while continuation:
                if deadline and time.monotonic() > deadline:
                    self._progress(f"Timeout reached ({len(comments)} comments)")
                    break

                if continuation == last_cursor:
                    break
                last_cursor = continuation

                page_num += 1

                try:
                    api_result = await page.evaluate(
                        """
                        async (continuation) => {
                            try {
                                const resp = await fetch(
                                    '/youtubei/v1/next?key="""
                        + INNERTUBE_API_KEY
                        + """', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-YouTube-Client-Name': '1',
                                        'X-YouTube-Client-Version': '"""
                        + INNERTUBE_CLIENT["clientVersion"]
                        + """',
                                    },
                                    body: JSON.stringify({
                                        context: {
                                            client: {
                                                clientName: 'WEB',
                                                clientVersion: '"""
                        + INNERTUBE_CLIENT["clientVersion"]
                        + """',
                                                hl: 'en',
                                                gl: 'US',
                                            }
                                        },
                                        continuation: continuation,
                                    }),
                                    credentials: 'include',
                                });
                                if (resp.ok) {
                                    return await resp.json();
                                }
                                return { _error: resp.status };
                            } catch(e) {
                                return { _error: e.message };
                            }
                        }
                    """,
                        continuation,
                    )
                except Exception as e:
                    self._progress("Could not load comments")
                    break

                if not api_result or "_error" in api_result:
                    error = api_result.get("_error") if api_result else "unknown"
                    if error == 429:
                        delay.on_rate_limit()
                        await delay.wait()
                        continue
                    delay.on_error()
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    await delay.wait()
                    continue

                # Parse response
                raw_comments, next_continuation, reply_conts = parse_comments_response(
                    api_result,
                )

                if not raw_comments:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                else:
                    consecutive_empty = 0

                for raw in raw_comments:
                    c = parse_comment(
                        raw, video_id, video_url, video_title, input_url,
                        threading_depth=0,
                    )
                    if c["id"] and c["id"] not in comment_ids_seen:
                        comment_ids_seen.add(c["id"])
                        comments.append(c)

                reply_continuations_all.extend(reply_conts)
                continuation = next_continuation
                delay.on_success()

                self._progress(f"Found {len(comments)} comments so far...")

                if self.max_comments > 0 and len(comments) >= self.max_comments:
                    comments = comments[: self.max_comments]
                    break

                await delay.wait()

            # Fetch replies (using aiohttp since we have cookies from browser)
            if self.max_replies >= 0 and reply_continuations_all:
                browser_cookies = await context.cookies()
                cookies_dict = {c["name"]: c["value"] for c in browser_cookies}
                reply_headers = {"User-Agent": USER_AGENT}

                reply_delay = AdaptiveDelay(
                    min_delay=0.5, max_delay=10.0, initial=2.0,
                )
                reply_connector = aiohttp.TCPConnector(limit=5, keepalive_timeout=30)
                async with aiohttp.ClientSession(
                    headers=reply_headers,
                    cookies=cookies_dict,
                    connector=reply_connector,
                ) as reply_session:
                    replies = await self._fetch_replies_innertube(
                        reply_session, reply_continuations_all, comment_ids_seen,
                        video_id, video_url, video_title, input_url,
                        reply_delay, deadline,
                    )
                    comments.extend(replies)

        except Exception as e:
            self._progress("Something went wrong loading comments")
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

    # -----------------------------------------------------------------------
    #  Main scrape method (cascade)
    # -----------------------------------------------------------------------

    async def scrape_video_comments(
        self, video_url: str, deadline: float = 0,
    ) -> list[dict]:
        """
        Main entry point: scrape all comments from a single YouTube video.
        Tries multiple methods in order of speed/reliability.
        Returns list[dict].
        """
        # Clean URL
        if not video_url.startswith("http"):
            video_url = f"https://{video_url}"

        input_url = video_url
        video_id = extract_video_id(video_url)
        if not video_id:
            self._progress(f"Invalid YouTube URL: {video_url}")
            return []

        # Normalize URL
        video_url = normalize_youtube_url(video_url)

        limit_text = f"{self.max_comments}" if self.max_comments > 0 else "all"
        self._progress(f"Processing: {video_url}")
        self._progress(f"Comment limit: {limit_text}")

        # Method 1: Direct API (fastest, no browser needed)
        comments = await self._scrape_comments_innertube(
            video_url, video_id, input_url, deadline,
        )

        # Method 2: yt-dlp (if direct API fails)
        if not comments and (not deadline or time.monotonic() < deadline):
            comments = await self._scrape_comments_ytdlp(
                video_url, video_id, input_url, deadline,
            )

        # Method 3: Playwright + InnerTube (last resort)
        if not comments and (not deadline or time.monotonic() < deadline):
            comments = await self._scrape_comments_playwright(
                video_url, video_id, input_url, deadline,
            )

        return comments
