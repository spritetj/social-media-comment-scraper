"""
Facebook Comments Scraper -- HTTP Only (No Playwright)
======================================================
Pure HTTP scraper using curl_cffi for TLS fingerprint impersonation.
No browser automation required. Works on Streamlit Cloud.

Approach:
  1) HTTP GET the page with Chrome TLS impersonation -> get HTML
  2) Regex extract tokens from HTML: fb_dtsg, lsd, jazoest
  3) Parse <script type="application/json"> tags for feedback_id,
     initial comments, and expansion tokens
  4) GraphQL POST for pagination and reply expansion
"""

import asyncio
import base64
import json
import random
import re
import time
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

DOC_ID_ROOT = "25750071871314498"
DOC_ID_PAGINATION = "26362559876663565"
DOC_ID_REPLIES = "25549931698036634"

MAX_PAGES = 200

# ──────────────────────────────────────────────
# URL Helpers
# ──────────────────────────────────────────────

def detect_url_type(url: str) -> str:
    if "/reel/" in url or "/reels/" in url:
        return "reel"
    if "/watch" in url:
        return "watch"
    if "/videos/" in url:
        return "video"
    if "photo.php" in url or "/photos/" in url:
        return "photo"
    return "post"


def extract_post_id_from_url(url: str) -> str:
    patterns = [
        r'/reel/(\d+)',
        r'[?&]v=(\d+)',
        r'fbid=(\d+)',
        r'story_fbid=(\d+)',
        r'/posts/[^/]+/(\d+)',
        r'/videos/[^/]+/(\d+)',
        r'(?:posts|videos|photos)/(\d+)',
        r'/(\d{10,})(?:[/?]|$)',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return ""


def build_feedback_id(post_id: str) -> str:
    raw = f"feedback:{post_id}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_fb_id(b64_id: str) -> str:
    try:
        return base64.b64decode(b64_id).decode("utf-8")
    except Exception:
        return b64_id

# ──────────────────────────────────────────────
# Comment Helpers
# ──────────────────────────────────────────────

def format_timestamp(ts) -> str:
    try:
        if isinstance(ts, (int, float)) and ts > 0:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        pass
    return str(ts) if ts else ""


def _is_comment(obj: dict) -> bool:
    body = obj.get("body")
    if not isinstance(body, dict) or "text" not in body:
        return False
    author = obj.get("author")
    if not isinstance(author, dict) or "name" not in author:
        return False
    return "created_time" in obj


def find_comments_in_data(data, results: list, depth: int = 0):
    """Recursively find Comment nodes in GraphQL/Relay data."""
    if depth > 30:
        return
    if isinstance(data, dict):
        if data.get("__typename") == "Comment" and "body" in data:
            results.append(data)
        elif _is_comment(data):
            results.append(data)
        for v in data.values():
            find_comments_in_data(v, results, depth + 1)
    elif isinstance(data, list):
        for item in data:
            find_comments_in_data(item, results, depth + 1)


def find_end_cursor(data, depth=0) -> str:
    """Find the pagination end_cursor for the main comments list."""
    if depth > 20:
        return ""
    if isinstance(data, dict):
        comments_conn = data.get("comments")
        if isinstance(comments_conn, dict):
            pi = comments_conn.get("page_info")
            if isinstance(pi, dict) and pi.get("end_cursor") and pi.get("has_next_page"):
                return pi["end_cursor"]

        cri = data.get("comment_rendering_instance_for_feed_location")
        if isinstance(cri, dict):
            result = find_end_cursor(cri, depth + 1)
            if result:
                return result

        for key, value in data.items():
            if key in ("replies_connection", "replies_fields"):
                continue
            result = find_end_cursor(value, depth + 1)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_end_cursor(item, depth + 1)
            if result:
                return result
    return ""


def find_expansion_tokens(data, tokens: dict, depth=0):
    """Find expansion_token values in GraphQL data."""
    if depth > 30:
        return
    if isinstance(data, dict):
        exp_token = data.get("expansion_token")
        if exp_token and isinstance(exp_token, str):
            fid = data.get("id", "")
            if not fid:
                feedback = data.get("feedback")
                if isinstance(feedback, dict):
                    fid = feedback.get("id", "")
            if fid:
                tokens[fid] = exp_token

        exp_info = data.get("expansion_info")
        if isinstance(exp_info, dict):
            exp_token2 = exp_info.get("expansion_token")
            if exp_token2 and isinstance(exp_token2, str):
                fid = data.get("id", "")
                if fid:
                    tokens[fid] = exp_token2

        for v in data.values():
            find_expansion_tokens(v, tokens, depth + 1)
    elif isinstance(data, list):
        for item in data:
            find_expansion_tokens(item, tokens, depth + 1)


def find_post_caption(data, feedback_id: str = "", depth: int = 0) -> tuple[str, int]:
    """Find the post caption (message.text) in parsed JSON data."""
    if depth > 25:
        return "", 0
    if isinstance(data, dict):
        tn = data.get("__typename", "")
        if tn == "Comment":
            return "", 0

        best_caption = ""
        best_priority = 0

        message = data.get("message")
        if isinstance(message, dict) and isinstance(message.get("text"), str) and message["text"]:
            feedback = data.get("feedback")
            has_feedback = isinstance(feedback, dict) and feedback.get("id")

            if has_feedback and feedback_id and feedback["id"] == feedback_id:
                return message["text"], 3
            elif has_feedback:
                best_caption = message["text"]
                best_priority = 2
            elif "Story" in tn or "Post" in tn:
                best_caption = message["text"]
                best_priority = 1

        for v in data.values():
            child_caption, child_priority = find_post_caption(v, feedback_id, depth + 1)
            if child_priority > best_priority:
                best_caption = child_caption
                best_priority = child_priority
                if best_priority == 3:
                    return best_caption, 3

        return best_caption, best_priority

    elif isinstance(data, list):
        best_caption = ""
        best_priority = 0
        for item in data:
            child_caption, child_priority = find_post_caption(item, feedback_id, depth + 1)
            if child_priority > best_priority:
                best_caption = child_caption
                best_priority = child_priority
                if best_priority == 3:
                    return best_caption, 3
        return best_caption, best_priority

    return "", 0


def format_comment(node: dict, post_url: str, input_url: str, post_caption: str = "") -> dict:
    """Format a raw comment node to output dict."""
    body = node.get("body", {})
    author = node.get("author", {})
    feedback = node.get("feedback", {}) or {}

    text = body.get("text", "") if isinstance(body, dict) else str(body)
    if not text or text == "None":
        text = ""

    profile_name = author.get("name", "") if isinstance(author, dict) else ""
    profile_id = author.get("id", "") if isinstance(author, dict) else ""

    profile_pic = ""
    if isinstance(author, dict):
        for pk in ("profile_picture_depth_0", "profile_picture", "profilePicture"):
            pd = author.get(pk)
            if isinstance(pd, dict):
                profile_pic = pd.get("uri", "")
                if profile_pic:
                    break

    profile_url = ""
    if isinstance(author, dict):
        profile_url = author.get("url", "")
        if not profile_url and profile_id:
            profile_url = f"https://www.facebook.com/{profile_id}"

    created_time = node.get("created_time", 0)
    date_str = format_timestamp(created_time) if created_time else ""

    likes_count = 0
    if isinstance(feedback, dict):
        reactors = feedback.get("reactors")
        if isinstance(reactors, dict):
            likes_count = reactors.get("count", 0)
            if not likes_count:
                cr = reactors.get("count_reduced", "0")
                if isinstance(cr, str) and cr.isdigit():
                    likes_count = int(cr)
        if not likes_count:
            top_r = feedback.get("top_reactions")
            if isinstance(top_r, dict):
                for edge in top_r.get("edges", []):
                    likes_count += edge.get("reaction_count", 0) if isinstance(edge, dict) else 0
        if not likes_count:
            i18n = feedback.get("i18n_reaction_count", "0")
            if isinstance(i18n, str) and i18n.isdigit():
                likes_count = int(i18n)

    comments_count = 0
    if isinstance(feedback, dict):
        rf = feedback.get("replies_fields")
        if isinstance(rf, dict):
            comments_count = rf.get("total_count", 0) or rf.get("count", 0)
        if not comments_count:
            comments_count = feedback.get("total_comment_count", 0)

    comment_url = ""
    if isinstance(feedback, dict):
        comment_url = feedback.get("url", "")
    if not comment_url:
        comment_url = node.get("url", "")

    threading_depth = node.get("depth", node.get("threading_depth", 0))

    return {
        "facebookUrl": post_url,
        "postCaption": post_caption,
        "commentUrl": comment_url,
        "id": node.get("id", ""),
        "date": date_str,
        "text": text,
        "profileName": profile_name,
        "profileId": profile_id,
        "profilePicture": profile_pic,
        "profileUrl": profile_url,
        "likesCount": str(likes_count),
        "commentsCount": comments_count,
        "threadingDepth": threading_depth,
        "inputUrl": input_url,
    }

# ──────────────────────────────────────────────
# GraphQL Response Parsing
# ──────────────────────────────────────────────

def parse_graphql_response(text: str) -> tuple[list[dict], str]:
    """Parse a GraphQL response into (comment_nodes, next_cursor)."""
    if text.startswith("for (;;);"):
        text = text[9:]

    comments = []
    next_cursor = ""
    json_objects = []

    try:
        json_objects.append(json.loads(text))
    except json.JSONDecodeError:
        for line in text.split("\n"):
            line = line.strip()
            if line:
                try:
                    json_objects.append(json.loads(line))
                except Exception:
                    pass

    for obj in json_objects:
        find_comments_in_data(obj, comments)
        c = find_end_cursor(obj)
        if c:
            next_cursor = c

    return comments, next_cursor


def parse_expansion_tokens_from_text(text: str) -> dict:
    """Extract expansion tokens from raw GraphQL response text."""
    if text.startswith("for (;;);"):
        text = text[9:]

    tokens = {}
    json_objects = []
    try:
        json_objects.append(json.loads(text))
    except json.JSONDecodeError:
        for line in text.split("\n"):
            line = line.strip()
            if line:
                try:
                    json_objects.append(json.loads(line))
                except Exception:
                    pass

    for obj in json_objects:
        find_expansion_tokens(obj, tokens)

    return tokens

# ──────────────────────────────────────────────
# Session Creation (curl_cffi with Chrome TLS)
# ──────────────────────────────────────────────

async def create_session(cookies: dict) -> AsyncSession:
    """Create a curl_cffi async session with Chrome TLS impersonation."""
    session = AsyncSession(impersonate="chrome")
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".facebook.com")
    return session

# ──────────────────────────────────────────────
# Phase 1: Page Fetch + Token Extraction
# ──────────────────────────────────────────────

async def fetch_page_and_tokens(
    session: AsyncSession, url: str, cookies: dict,
    progress_fn=None,
) -> dict:
    """Fetch page HTML and extract all tokens/data needed for GraphQL calls."""
    def _progress(msg):
        if progress_fn:
            progress_fn(msg)

    result = {
        "fb_dtsg": "",
        "lsd": "",
        "jazoest": "",
        "user_id": cookies.get("c_user", ""),
        "feedback_id": "",
        "initial_comments": [],
        "initial_cursor": "",
        "expansion_tokens": {},
        "post_caption": "",
        "url_type": detect_url_type(url),
    }

    # Fetch page
    try:
        resp = await session.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            allow_redirects=True,
            timeout=30,
        )
        html = resp.text
    except Exception as e:
        _progress(f"Failed to fetch page: {e}")
        return result

    if not html:
        _progress("Empty HTML response")
        return result

    # Page fetched successfully

    # Extract tokens from HTML via regex
    m = re.search(r'"DTSGInitialData".*?"token":"([^"]+)"', html)
    if m:
        result["fb_dtsg"] = m.group(1)
    else:
        m = re.search(r'fb_dtsg.*?value":"([^"]+)"', html)
        if m:
            result["fb_dtsg"] = m.group(1)

    m = re.search(r'"LSD".*?"token":"([^"]+)"', html)
    if m:
        result["lsd"] = m.group(1)

    m = re.search(r'jazoest[=:](\d+)', html)
    if m:
        result["jazoest"] = m.group(1)

    url_post_id = extract_post_id_from_url(url)
    url_type = result["url_type"]
    url_id_reliable = url_type not in ("photo",)

    # Extract feedback_ids from HTML
    all_fids = []

    for m in re.finditer(r'"feedback_id":"([^"]+)"', html):
        fid = m.group(1)
        if fid not in all_fids:
            all_fids.append(fid)

    for m in re.finditer(r'"feedback"\s*:\s*\{\s*"id"\s*:\s*"([A-Za-z0-9+/=]+)"', html):
        fid = m.group(1)
        try:
            decoded = base64.b64decode(fid).decode("utf-8")
            if decoded.startswith("feedback:") and fid not in all_fids:
                all_fids.append(fid)
        except Exception:
            pass

    # Strategy 1: URL match
    decoded_fids = [(fid, decode_fb_id(fid)) for fid in all_fids]

    if url_id_reliable and url_post_id:
        for fid, decoded in decoded_fids:
            if decoded == f"feedback:{url_post_id}":
                result["feedback_id"] = fid
                break

    # Strategy 2: Heuristic
    if not result["feedback_id"]:
        top_level = [(fid, d) for fid, d in decoded_fids
                     if d.startswith("feedback:") and "_" not in d]
        if top_level:
            best_fid = ""
            best_count = 0
            for fid, decoded in top_level:
                prefix = decoded + "_"
                count = sum(1 for _, d in decoded_fids if d.startswith(prefix))
                if count > best_count:
                    best_count = count
                    best_fid = fid
            result["feedback_id"] = best_fid or top_level[0][0]
        elif all_fids:
            result["feedback_id"] = all_fids[0]

    # Strategy 3: Construct from URL
    if not result["feedback_id"] and url_post_id and url_type == "post":
        result["feedback_id"] = build_feedback_id(url_post_id)

    # Parse initial comments and expansion tokens from embedded JSON scripts
    script_pattern = re.compile(
        r'<script\s+type="application/json"[^>]*>(.*?)</script>',
        re.DOTALL,
    )

    comment_ids = set()
    caption_priority = 0

    for match in script_pattern.finditer(html):
        script_text = match.group(1).strip()
        if not script_text:
            continue

        if '"Comment"' not in script_text and '"body"' not in script_text:
            if '"expansion_token"' not in script_text and '"message"' not in script_text:
                continue

        try:
            data = json.loads(script_text)
        except json.JSONDecodeError:
            continue

        if '"Comment"' in script_text or '"body"' in script_text:
            nodes = []
            find_comments_in_data(data, nodes)
            for n in nodes:
                cid = n.get("id", "")
                if cid and cid not in comment_ids:
                    comment_ids.add(cid)
                    result["initial_comments"].append(n)

        cursor = find_end_cursor(data)
        if cursor and not result["initial_cursor"]:
            result["initial_cursor"] = cursor

        find_expansion_tokens(data, result["expansion_tokens"])

        cap_text, cap_pri = find_post_caption(data, result["feedback_id"])
        if cap_pri > caption_priority:
            result["post_caption"] = cap_text
            caption_priority = cap_pri

    # Fallback caption from og:description
    if not result["post_caption"]:
        m = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
        if m:
            result["post_caption"] = m.group(1)

    return result

# ──────────────────────────────────────────────
# GraphQL API Calls
# ──────────────────────────────────────────────

async def graphql_post(session: AsyncSession, form_data: dict) -> str:
    """POST to Facebook's GraphQL API with Chrome TLS impersonation."""
    try:
        resp = await session.post(
            "https://www.facebook.com/api/graphql/",
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
                "X-FB-Friendly-Name": form_data.get("fb_api_req_friendly_name", ""),
                "X-FB-LSD": form_data.get("lsd", ""),
                "X-ASBD-ID": "359341",
                "Origin": "https://www.facebook.com",
                "Referer": "https://www.facebook.com/",
            },
            timeout=20,
        )
        return resp.text or ""
    except Exception as e:
        return json.dumps({"error": str(e)})


async def fetch_root_comments(
    session: AsyncSession, tokens: dict,
    feed_location: str = "POST_PERMALINK_DIALOG",
) -> tuple[str, list[dict], str]:
    """Make the initial root comment query."""
    variables = {
        "commentsIntentToken": "REVERSE_CHRONOLOGICAL_UNFILTERED_INTENT_V1",
        "feedLocation": feed_location,
        "feedbackSource": 2,
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": tokens["feedback_id"],
        "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
        "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
        "__relay_internal__pv__IsWorkUserrelayprovider": False,
    }

    form_data = {
        "av": tokens["user_id"],
        "__user": tokens["user_id"],
        "__a": "1",
        "fb_dtsg": tokens["fb_dtsg"],
        "lsd": tokens["lsd"],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "CommentListComponentsRootQuery",
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID_ROOT,
    }
    if tokens.get("jazoest"):
        form_data["jazoest"] = tokens["jazoest"]

    raw_text = await graphql_post(session, form_data)
    comments, next_cursor = parse_graphql_response(raw_text)
    return raw_text, comments, next_cursor


async def fetch_comments_page(
    session: AsyncSession, tokens: dict,
    cursor: str,
    feed_location: str = "POST_PERMALINK_DIALOG",
) -> tuple[str, list[dict], str]:
    """Fetch a page of comments using pagination cursor."""
    variables = {
        "commentsAfterCount": -1,
        "commentsAfterCursor": cursor,
        "commentsBeforeCount": None,
        "commentsBeforeCursor": None,
        "commentsIntentToken": "REVERSE_CHRONOLOGICAL_UNFILTERED_INTENT_V1",
        "feedLocation": feed_location,
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": tokens["feedback_id"],
        "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
        "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
        "__relay_internal__pv__IsWorkUserrelayprovider": False,
    }

    form_data = {
        "av": tokens["user_id"],
        "__user": tokens["user_id"],
        "__a": "1",
        "fb_dtsg": tokens["fb_dtsg"],
        "lsd": tokens["lsd"],
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "CommentsListComponentsPaginationQuery",
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID_PAGINATION,
    }
    if tokens.get("jazoest"):
        form_data["jazoest"] = tokens["jazoest"]

    raw_text = await graphql_post(session, form_data)
    comments, next_cursor = parse_graphql_response(raw_text)
    return raw_text, comments, next_cursor


async def fetch_replies_batch(
    session: AsyncSession, tokens: dict,
    batch: list[dict],
    feed_location: str = "POST_PERMALINK_DIALOG",
) -> list[tuple[str, list[dict]]]:
    """Fetch replies for multiple comments concurrently."""
    tasks = []
    for item in batch:
        variables = {
            "clientKey": None,
            "expansionToken": item["expansion_token"],
            "feedLocation": feed_location,
            "focusCommentID": None,
            "repliesAfterCount": None,
            "repliesAfterCursor": None,
            "repliesBeforeCount": None,
            "repliesBeforeCursor": None,
            "scale": 2,
            "useDefaultActor": False,
            "id": item["feedback_id"],
            "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
            "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
            "__relay_internal__pv__IsWorkUserrelayprovider": False,
        }

        form_data = {
            "av": tokens["user_id"],
            "__user": tokens["user_id"],
            "__a": "1",
            "fb_dtsg": tokens["fb_dtsg"],
            "lsd": tokens["lsd"],
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": "Depth1CommentsListPaginationQuery",
            "server_timestamps": "true",
            "variables": json.dumps(variables),
            "doc_id": DOC_ID_REPLIES,
        }
        if tokens.get("jazoest"):
            form_data["jazoest"] = tokens["jazoest"]

        tasks.append(graphql_post(session, form_data))

    raw_texts = await asyncio.gather(*tasks)

    results = []
    for raw_text in raw_texts:
        comments, _ = parse_graphql_response(raw_text)
        results.append((raw_text, comments))
    return results

# ──────────────────────────────────────────────
# Cookie Conversion
# ──────────────────────────────────────────────

def _convert_cookies(cookies: list[dict] | dict | None) -> dict:
    """Convert Playwright-format cookies (list of dicts) to simple {name: value} dict."""
    if cookies is None:
        return {}
    if isinstance(cookies, dict):
        return cookies
    result = {}
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name and value:
            result[name] = value
    return result

# ──────────────────────────────────────────────
# Main Scraper
# ──────────────────────────────────────────────

async def scrape_comments_fast(
    post_url: str,
    cookies: list[dict] | dict = None,
    progress_callback: callable = None,
) -> list[dict]:
    """Scrape all comments from a Facebook post URL.

    Args:
        post_url: The Facebook post URL to scrape.
        cookies: Playwright-format cookies (list of dicts) or simple {name: value} dict.
        progress_callback: Optional callable(msg: str) for progress updates.

    Returns:
        List of formatted comment dicts.
    """
    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    # Convert cookies to simple dict format
    cookie_dict = _convert_cookies(cookies)

    if not cookie_dict:
        _progress("No cookies provided. Facebook requires authentication.")
        return []

    start_time = time.time()
    url_type = detect_url_type(post_url)
    _progress(f"Processing: {post_url}")

    # Create session with Chrome TLS impersonation
    session = await create_session(cookie_dict)

    try:
        # Phase 1: Fetch page and extract tokens
        _progress("Loading post...")
        phase1_start = time.time()
        tokens = await fetch_page_and_tokens(session, post_url, cookie_dict, progress_fn=_progress)
        phase1_time = time.time() - phase1_start

        if not tokens["fb_dtsg"]:
            _progress("Authentication failed. Please check your cookies.")
            return []

        if not tokens["feedback_id"]:
            _progress("Could not identify this post. Please check the URL.")
            return []

        if tokens["post_caption"]:
            preview = tokens["post_caption"][:80] + ("..." if len(tokens["post_caption"]) > 80 else "")
            _progress(f"Caption: {preview}")

        # Collect all comments
        comment_ids = set()
        all_comments = []
        expansion_tokens = dict(tokens.get("expansion_tokens", {}))

        for node in tokens["initial_comments"]:
            cid = node.get("id", "")
            if cid and cid not in comment_ids:
                comment_ids.add(cid)
                all_comments.append(node)

        # Determine feed_location
        feed_location = "POST_PERMALINK_DIALOG"
        if url_type in ("reel", "watch", "video"):
            feed_location = "DEDICATED_COMMENTING_SURFACE"

        # Phase 2: Paginate via GraphQL API
        _progress("Fetching comments...")
        phase2_start = time.time()

        # Root query
        raw_root, root_comments, cursor = await fetch_root_comments(
            session, tokens, feed_location=feed_location,
        )

        for node in root_comments:
            cid = node.get("id", "")
            if cid and cid not in comment_ids:
                comment_ids.add(cid)
                all_comments.append(node)

        root_tokens = parse_expansion_tokens_from_text(raw_root)
        expansion_tokens.update(root_tokens)

        if root_comments:
            _progress(f"Found {len(root_comments)} initial comments")

        # Retry with alternate feed locations for reel/watch/video
        if not root_comments and not cursor and url_type in ("reel", "watch", "video"):
            alt_locations = [
                "DEDICATED_COMMENTING_SURFACE",
                "VIDEO_PERMALINK",
                "TAHOE",
                "POST_PERMALINK_DIALOG",
                "POST_PERMALINK_VIEW",
            ]
            alt_locations = [fl for fl in alt_locations if fl != feed_location]
            for alt_fl in alt_locations:
                # Try alternate query
                raw_root2, root_comments2, cursor2 = await fetch_root_comments(
                    session, tokens, feed_location=alt_fl,
                )
                if root_comments2 or cursor2:
                    feed_location = alt_fl
                    cursor = cursor2
                    root_tokens2 = parse_expansion_tokens_from_text(raw_root2)
                    expansion_tokens.update(root_tokens2)
                    for node in root_comments2:
                        cid = node.get("id", "")
                        if cid and cid not in comment_ids:
                            comment_ids.add(cid)
                            all_comments.append(node)
                    _progress(f"Found {len(root_comments2)} comments")
                    break
                await asyncio.sleep(0.1)

        # Use initial cursor as fallback
        if not cursor:
            cursor = tokens.get("initial_cursor", "")

        # Paginate
        page_num = 0
        consecutive_empty = 0

        while cursor and page_num < MAX_PAGES:
            page_num += 1

            raw_text, page_comments, next_cursor = await fetch_comments_page(
                session, tokens, cursor, feed_location=feed_location,
            )

            new_count = 0
            for node in page_comments:
                cid = node.get("id", "")
                if cid and cid not in comment_ids:
                    comment_ids.add(cid)
                    all_comments.append(node)
                    new_count += 1

            page_tokens = parse_expansion_tokens_from_text(raw_text)
            expansion_tokens.update(page_tokens)

            if new_count > 0:
                _progress(f"Found {len(all_comments)} comments so far...")
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break

            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            await asyncio.sleep(random.uniform(0.1, 0.3))

        phase2_time = time.time() - phase2_start

        # Phase 3: Expand reply threads
        _progress("Loading replies...")
        phase3_start = time.time()
        reply_count_before = len(all_comments)

        fetched_feedback_ids = set()
        REPLY_BATCH_SIZE = 10
        max_depth_passes = 5

        for depth_pass in range(max_depth_passes):
            reply_items = []
            for node in all_comments:
                feedback = node.get("feedback", {})
                if not isinstance(feedback, dict):
                    continue
                reply_count = 0
                rf = feedback.get("replies_fields")
                if isinstance(rf, dict):
                    reply_count = rf.get("total_count", 0) or rf.get("count", 0)
                if not reply_count:
                    reply_count = feedback.get("total_comment_count", 0)
                if reply_count and reply_count > 0:
                    cfid = feedback.get("id", "")
                    if cfid and cfid not in fetched_feedback_ids:
                        exp_token = expansion_tokens.get(cfid, "")
                        if exp_token:
                            reply_items.append({
                                "feedback_id": cfid,
                                "expansion_token": exp_token,
                                "reply_count": reply_count,
                            })
                            fetched_feedback_ids.add(cfid)

            if not reply_items:
                break

            # Expanding reply threads

            pass_new = 0
            for batch_start in range(0, len(reply_items), REPLY_BATCH_SIZE):
                batch = reply_items[batch_start:batch_start + REPLY_BATCH_SIZE]
                batch_results = await fetch_replies_batch(
                    session, tokens, batch, feed_location=feed_location,
                )

                for raw_reply, reply_nodes in batch_results:
                    reply_exp_tokens = parse_expansion_tokens_from_text(raw_reply)
                    expansion_tokens.update(reply_exp_tokens)
                    for node in reply_nodes:
                        cid = node.get("id", "")
                        if cid and cid not in comment_ids:
                            comment_ids.add(cid)
                            all_comments.append(node)
                            pass_new += 1

            if pass_new > 0:
                _progress(f"Found {len(all_comments)} comments so far...")
            else:
                break

        phase3_time = time.time() - phase3_start

    finally:
        await session.close()

    # Format results
    post_caption = tokens.get("post_caption", "")
    formatted = []
    for node in all_comments:
        formatted.append(format_comment(node, post_url, post_url, post_caption=post_caption))

    elapsed = time.time() - start_time
    top_level = sum(1 for c in formatted if c.get("threadingDepth", 0) == 0)
    replies = len(formatted) - top_level

    _progress(f"Done! {len(formatted)} comments found.")

    return formatted
