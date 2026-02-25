"""
Instagram Comment Scraper -- Web App Edition (HTTP Only)
========================================================
Pure HTTP scraper using aiohttp. No Playwright / no browser required.
Works on Streamlit Cloud.

Two-tier approach:
  1) Fetch post HTML, parse embedded JSON from <script type="application/json">
     tags to get initial comments + post metadata.
  2a) Authenticated (cookies): paginate via REST API endpoints.
  2b) Unauthenticated: paginate via GraphQL POST.
"""

import asyncio
import json
import random
import re
from datetime import datetime, timezone

import aiohttp

# ──────────────────────────────────────────────
# Constants & Config
# ──────────────────────────────────────────────

CHROME_VERSION = "133"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"
)

DEFAULT_IG_APP_ID = "936619743392459"
MAX_PAGES = 200
PAGE_DELAY_MIN = 1.0
PAGE_DELAY_MAX = 2.5
COMMENTS_PER_PAGE = 50

GRAPHQL_DOC_IDS = [
    "8845758582119845",
    "7803498539768460",
    "9064463823609386",
]

_NAV_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def _api_headers(csrf_token: str) -> dict:
    """Headers for Instagram REST API / GraphQL XHR calls."""
    return {
        "Accept": "*/*",
        "X-CSRFToken": csrf_token,
        "X-IG-App-ID": DEFAULT_IG_APP_ID,
        "X-Requested-With": "XMLHttpRequest",
        "X-ASBD-ID": "129477",
        "X-IG-WWW-Claim": "0",
        "Referer": "https://www.instagram.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

# ──────────────────────────────────────────────
# URL Helpers
# ──────────────────────────────────────────────

def detect_url_type(url: str) -> str:
    if "/stories/" in url:
        return "story"
    if "/reel/" in url or "/reels/" in url:
        return "reel"
    if "/tv/" in url:
        return "igtv"
    if "/p/" in url:
        return "post"
    return "unknown"


def extract_shortcode(url: str) -> str | None:
    match = re.search(r"/(p|reel|reels|tv)/([A-Za-z0-9_-]+)", url)
    return match.group(2) if match else None


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    if "instagram.com" not in url:
        return url
    url = re.sub(
        r"https?://(www\.)?instagram\.com",
        "https://www.instagram.com",
        url,
    )
    url = re.sub(r"[?&](utm_source|igsh|igshid|ig_web_copy_link)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url

# ──────────────────────────────────────────────
# JSON Tree Traversal
# ──────────────────────────────────────────────

def find_key_recursive(data, target_key, max_depth=30, _depth=0):
    if _depth > max_depth:
        return None
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for v in data.values():
            result = find_key_recursive(v, target_key, max_depth, _depth + 1)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_key_recursive(item, target_key, max_depth, _depth + 1)
            if result is not None:
                return result
    return None

# ──────────────────────────────────────────────
# Comment Formatting
# ──────────────────────────────────────────────

def format_comment_v2(
    node: dict, post_url: str, input_url: str,
    depth: int = 0, caption_text: str = "",
) -> dict | None:
    """Format a comment from the new xdt_api format."""
    if not node or not isinstance(node, dict):
        return None

    text = node.get("text", "")
    comment_id = str(node.get("pk", node.get("id", "")))
    if not text and not comment_id:
        return None

    user = node.get("user", {})
    if not isinstance(user, dict):
        user = {}

    created_at = node.get("created_at", node.get("created_at_utc", 0))
    try:
        timestamp = int(created_at)
        date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        timestamp = 0
        date_str = ""

    likes_count = 0
    if isinstance(node.get("comment_like_count"), int):
        likes_count = node["comment_like_count"]

    child_count = node.get("child_comment_count", 0) or 0

    return {
        "instagramUrl": post_url,
        "id": comment_id,
        "text": text,
        "date": date_str,
        "timestamp": timestamp,
        "ownerUsername": user.get("username", ""),
        "ownerId": str(user.get("pk", user.get("id", ""))),
        "ownerIsVerified": user.get("is_verified", False),
        "ownerProfilePicUrl": user.get("profile_pic_url", ""),
        "likesCount": likes_count,
        "repliesCount": child_count,
        "threadingDepth": depth,
        "inputUrl": input_url,
        "captionText": caption_text,
    }


def format_comment_v1(
    node: dict, post_url: str, input_url: str,
    depth: int = 0, caption_text: str = "",
) -> dict | None:
    """Format a comment from the legacy xdt_shortcode_media format."""
    if not node or not isinstance(node, dict):
        return None

    text = node.get("text", "")
    comment_id = node.get("id", node.get("pk", ""))
    if not text and not comment_id:
        return None

    owner = node.get("owner", node.get("user", {}))
    if not isinstance(owner, dict):
        owner = {}

    created_at = node.get("created_at", node.get("created_time", 0))
    try:
        timestamp = int(created_at)
        date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        timestamp = 0
        date_str = ""

    likes_count = 0
    edge_liked = node.get("edge_liked_by", {})
    if isinstance(edge_liked, dict):
        likes_count = edge_liked.get("count", 0)
    if not likes_count and isinstance(node.get("comment_like_count"), int):
        likes_count = node["comment_like_count"]

    replies_count = 0
    threaded = node.get("edge_threaded_comments", {})
    if isinstance(threaded, dict):
        replies_count = threaded.get("count", 0)
    if not replies_count:
        replies_count = node.get("child_comment_count", 0) or 0

    return {
        "instagramUrl": post_url,
        "id": str(comment_id),
        "text": text,
        "date": date_str,
        "timestamp": timestamp,
        "ownerUsername": owner.get("username", ""),
        "ownerId": str(owner.get("id", owner.get("pk", ""))),
        "ownerIsVerified": owner.get("is_verified", False),
        "ownerProfilePicUrl": owner.get("profile_pic_url", ""),
        "likesCount": likes_count,
        "repliesCount": replies_count,
        "threadingDepth": depth,
        "inputUrl": input_url,
        "captionText": caption_text,
    }


def extract_comments_from_edges_v1(
    edges: list, post_url: str, input_url: str,
    depth: int = 0, caption_text: str = "",
) -> list[dict]:
    """Extract comments from legacy GraphQL edge list."""
    comments = []
    for edge in edges:
        node = edge.get("node", edge)
        comment = format_comment_v1(
            node, post_url, input_url, depth, caption_text=caption_text,
        )
        if comment:
            comments.append(comment)
        threaded = node.get("edge_threaded_comments", {})
        reply_edges = threaded.get("edges", [])
        if reply_edges:
            replies = extract_comments_from_edges_v1(
                reply_edges, post_url, input_url,
                depth=1, caption_text=caption_text,
            )
            comments.extend(replies)
    return comments

# ──────────────────────────────────────────────
# Session Setup (aiohttp)
# ──────────────────────────────────────────────

async def init_session(
    cookies: dict | None = None,
) -> tuple[aiohttp.ClientSession, str, bool]:
    """Create an aiohttp session with Instagram headers.
    Returns (session, csrf_token, has_auth)."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-Ch-Ua": f'"Google Chrome";v="{CHROME_VERSION}", "Not?A_Brand";v="99", "Chromium";v="{CHROME_VERSION}"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
    }

    jar = aiohttp.CookieJar()
    session = aiohttp.ClientSession(headers=headers, cookie_jar=jar)

    csrf_token = ""
    has_auth = False
    if cookies:
        for name, value in cookies.items():
            session.cookie_jar.update_cookies(
                {name: value},
                response_url=aiohttp.client.URL("https://www.instagram.com/"),
            )
            if name == "csrftoken":
                csrf_token = value
            if name == "sessionid":
                has_auth = True

    # If no CSRF token from cookies, visit the homepage to get one
    if not csrf_token:
        try:
            async with session.get(
                "https://www.instagram.com/",
                headers=_NAV_HEADERS,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                for cookie in session.cookie_jar:
                    if cookie.key == "csrftoken":
                        csrf_token = cookie.value
                        break
        except Exception:
            pass

    return session, csrf_token, has_auth

# ──────────────────────────────────────────────
# HTML Fetch & Relay Data Extraction
# ──────────────────────────────────────────────

async def fetch_page_html(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch the post page HTML."""
    try:
        async with session.get(
            url,
            headers=_NAV_HEADERS,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return ""
            return await resp.text()
    except Exception:
        return ""


def extract_relay_data(html: str) -> dict:
    """Extract embedded relay data from Instagram HTML."""
    result = {"web_info": None, "comments": None, "shortcode_media": None}

    pattern = re.compile(
        r'<script\s+type="application/json"[^>]*>(.*?)</script>',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        script_text = match.group(1).strip()
        if not script_text:
            continue
        try:
            parsed = json.loads(script_text)
        except json.JSONDecodeError:
            continue

        # New format: xdt_api__v1__media__shortcode__web_info
        if not result["web_info"]:
            web_info = find_key_recursive(parsed, "xdt_api__v1__media__shortcode__web_info")
            if web_info and isinstance(web_info, dict):
                items = web_info.get("items", [])
                if items and isinstance(items[0], dict):
                    item = items[0]
                    caption = item.get("caption") or {}
                    user = item.get("user") or {}
                    preview_comments = []
                    for c in item.get("preview_comments", []):
                        cu = c.get("user") or {}
                        preview_comments.append({
                            "pk": c.get("pk"),
                            "text": c.get("text", ""),
                            "username": cu.get("username", ""),
                            "user_pk": cu.get("pk", ""),
                            "user_id": cu.get("id", ""),
                            "is_verified": cu.get("is_verified", False),
                            "profile_pic_url": cu.get("profile_pic_url", ""),
                            "created_at": c.get("created_at"),
                        })
                    result["web_info"] = {
                        "code": item.get("code"),
                        "pk": item.get("pk"),
                        "id": item.get("id"),
                        "comment_count": item.get("comment_count"),
                        "like_count": item.get("like_count"),
                        "username": user.get("username", ""),
                        "caption_text": caption.get("text", "") if isinstance(caption, dict) else "",
                        "taken_at": item.get("taken_at"),
                        "media_type": item.get("media_type"),
                        "preview_comments": preview_comments,
                    }

        # New format: xdt_api__v1__media__media_id__comments__connection
        if not result["comments"]:
            comments_conn = find_key_recursive(
                parsed, "xdt_api__v1__media__media_id__comments__connection",
            )
            if comments_conn and isinstance(comments_conn, dict):
                edges = []
                for e in comments_conn.get("edges", []):
                    n = e.get("node", {})
                    nu = n.get("user") or {}
                    edges.append({
                        "pk": n.get("pk"),
                        "text": n.get("text", ""),
                        "created_at": n.get("created_at", 0),
                        "child_comment_count": n.get("child_comment_count", 0),
                        "comment_like_count": n.get("comment_like_count"),
                        "username": nu.get("username", ""),
                        "user_pk": nu.get("pk", nu.get("id", "")),
                        "is_verified": nu.get("is_verified", False),
                        "profile_pic_url": nu.get("profile_pic_url", ""),
                        "parent_comment_id": n.get("parent_comment_id"),
                        "typename": n.get("__typename"),
                    })
                page_info = comments_conn.get("page_info") or {}
                result["comments"] = {
                    "edges": edges,
                    "has_next_page": page_info.get("has_next_page", False),
                    "end_cursor": page_info.get("end_cursor"),
                }

        # Legacy format: xdt_shortcode_media
        if not result["shortcode_media"]:
            media = find_key_recursive(parsed, "xdt_shortcode_media")
            if not media:
                media = find_key_recursive(parsed, "shortcode_media")
            if media and isinstance(media, dict) and media.get("id"):
                ce = (
                    media.get("edge_media_to_parent_comment")
                    or media.get("edge_media_to_comment")
                    or {}
                )
                edges = []
                for e in ce.get("edges", []):
                    n = e.get("node", {})
                    edge_owner = n.get("owner") or n.get("user") or {}
                    reply_edges = []
                    threaded = n.get("edge_threaded_comments") or {}
                    for re_edge in threaded.get("edges", []):
                        rn = re_edge.get("node", {})
                        rowner = rn.get("owner") or rn.get("user") or {}
                        reply_edges.append({
                            "id": rn.get("id"),
                            "text": rn.get("text", ""),
                            "created_at": rn.get("created_at", 0),
                            "username": rowner.get("username", ""),
                            "user_id": rowner.get("id", ""),
                            "is_verified": rowner.get("is_verified", False),
                            "profile_pic_url": rowner.get("profile_pic_url", ""),
                            "likes": (
                                rn.get("edge_liked_by", {}).get("count", 0)
                                if isinstance(rn.get("edge_liked_by"), dict)
                                else (rn.get("comment_like_count", 0))
                            ),
                        })
                    edges.append({
                        "id": n.get("id"),
                        "text": n.get("text", ""),
                        "created_at": n.get("created_at", 0),
                        "username": edge_owner.get("username", ""),
                        "user_id": edge_owner.get("id", ""),
                        "is_verified": edge_owner.get("is_verified", False),
                        "profile_pic_url": edge_owner.get("profile_pic_url", ""),
                        "likes": (
                            n.get("edge_liked_by", {}).get("count", 0)
                            if isinstance(n.get("edge_liked_by"), dict)
                            else (n.get("comment_like_count", 0))
                        ),
                        "replies_count": (
                            threaded.get("count", 0)
                            if isinstance(threaded, dict)
                            else (n.get("child_comment_count", 0))
                        ),
                        "reply_edges": reply_edges,
                    })
                ce_page_info = ce.get("page_info") or {}
                result["shortcode_media"] = {
                    "id": media.get("id"),
                    "shortcode": media.get("shortcode"),
                    "typename": media.get("__typename"),
                    "comment_count": ce.get("count", 0),
                    "has_next_page": ce_page_info.get("has_next_page", False),
                    "end_cursor": ce_page_info.get("end_cursor"),
                    "edges": edges,
                }

        if result["web_info"] and result["comments"]:
            break

    return result

# ──────────────────────────────────────────────
# REST API (Authenticated)
# ──────────────────────────────────────────────

async def fetch_comments_rest(
    session: aiohttp.ClientSession,
    media_pk: str,
    csrf_token: str,
    min_id: str | None = None,
) -> dict | None:
    """Fetch top-level comments via REST API (requires auth cookies)."""
    url = f"https://www.instagram.com/api/v1/media/{media_pk}/comments/"
    params = {"can_support_threading": "true", "permalink_enabled": "false"}
    if min_id:
        params["min_id"] = min_id

    try:
        async with session.get(
            url, params=params, headers=_api_headers(csrf_token),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return {"__error": True, "status": resp.status}
            text = await resp.text()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"__error": True, "message": "Not JSON"}
    except Exception as e:
        return {"__error": True, "message": str(e)}


async def fetch_child_comments(
    session: aiohttp.ClientSession,
    media_pk: str,
    comment_pk: str,
    csrf_token: str,
    max_id: str | None = None,
) -> dict | None:
    """Fetch reply/child comments for a specific parent comment via REST API."""
    url = f"https://www.instagram.com/api/v1/media/{media_pk}/comments/{comment_pk}/child_comments/"
    params = {}
    if max_id:
        params["max_id"] = max_id

    try:
        async with session.get(
            url, params=params, headers=_api_headers(csrf_token),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return {"__error": True, "status": resp.status}
            text = await resp.text()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"__error": True, "message": "Not JSON"}
    except Exception as e:
        return {"__error": True, "message": str(e)}

# ──────────────────────────────────────────────
# GraphQL Pagination (Unauthenticated Fallback)
# ──────────────────────────────────────────────

async def graphql_query(
    session: aiohttp.ClientSession,
    doc_id: str,
    variables: dict,
    csrf_token: str,
) -> dict | None:
    """Execute a GraphQL query via POST to /graphql/query/."""
    url = "https://www.instagram.com/graphql/query/"
    form_data = {
        "doc_id": doc_id,
        "variables": json.dumps(variables),
    }
    headers = {**_api_headers(csrf_token), "Content-Type": "application/x-www-form-urlencoded"}
    try:
        async with session.post(
            url, data=form_data, headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return {"__error": True, "status": resp.status}
            text = await resp.text()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"__error": True, "message": "Not JSON"}
    except Exception as e:
        return {"__error": True, "message": str(e)}

async def fetch_media_via_graphql(
    session: aiohttp.ClientSession,
    shortcode: str,
    csrf_token: str,
) -> dict | None:
    """Fetch post media info + initial comments via GraphQL.

    Returns a dict compatible with the legacy ``shortcode_media`` format
    used by the rest of the scraper, or *None* on failure.
    """
    for doc_id in GRAPHQL_DOC_IDS:
        result = await graphql_query(
            session, doc_id,
            {"shortcode": shortcode, "first": 50},
            csrf_token,
        )
        if not result or result.get("__error"):
            continue
        media = (
            find_key_recursive(result, "xdt_shortcode_media")
            or find_key_recursive(result, "shortcode_media")
        )
        if not media or not isinstance(media, dict) or not media.get("id"):
            continue

        ce = (
            media.get("edge_media_to_parent_comment")
            or media.get("edge_media_to_comment")
            or {}
        )
        edges = []
        for e in ce.get("edges", []):
            n = e.get("node", {})
            edge_owner = n.get("owner") or n.get("user") or {}
            reply_edges = []
            threaded = n.get("edge_threaded_comments") or {}
            for re_edge in threaded.get("edges", []):
                rn = re_edge.get("node", {})
                rowner = rn.get("owner") or rn.get("user") or {}
                reply_edges.append({
                    "id": rn.get("id"),
                    "text": rn.get("text", ""),
                    "created_at": rn.get("created_at", 0),
                    "username": rowner.get("username", ""),
                    "user_id": rowner.get("id", ""),
                    "is_verified": rowner.get("is_verified", False),
                    "profile_pic_url": rowner.get("profile_pic_url", ""),
                    "likes": (
                        rn.get("edge_liked_by", {}).get("count", 0)
                        if isinstance(rn.get("edge_liked_by"), dict)
                        else rn.get("comment_like_count", 0)
                    ),
                })
            edges.append({
                "id": n.get("id"),
                "text": n.get("text", ""),
                "created_at": n.get("created_at", 0),
                "username": edge_owner.get("username", ""),
                "user_id": edge_owner.get("id", ""),
                "is_verified": edge_owner.get("is_verified", False),
                "profile_pic_url": edge_owner.get("profile_pic_url", ""),
                "likes": (
                    n.get("edge_liked_by", {}).get("count", 0)
                    if isinstance(n.get("edge_liked_by"), dict)
                    else n.get("comment_like_count", 0)
                ),
                "replies_count": (
                    threaded.get("count", 0)
                    if isinstance(threaded, dict)
                    else n.get("child_comment_count", 0)
                ),
                "reply_edges": reply_edges,
            })
        ce_page_info = ce.get("page_info") or {}

        # Extract caption
        caption_text = ""
        cap = media.get("edge_media_to_caption", {})
        if isinstance(cap, dict):
            cap_edges = cap.get("edges", [])
            if cap_edges:
                caption_text = cap_edges[0].get("node", {}).get("text", "")

        return {
            "id": media["id"],
            "shortcode": media.get("shortcode"),
            "typename": media.get("__typename"),
            "comment_count": ce.get("count", 0),
            "has_next_page": ce_page_info.get("has_next_page", False),
            "end_cursor": ce_page_info.get("end_cursor"),
            "edges": edges,
            "caption_text": caption_text,
        }
    return None


# ──────────────────────────────────────────────
# Single Post Scraper
# ──────────────────────────────────────────────

async def scrape_single_post(
    url: str,
    cookies: dict | None = None,
    progress_callback: callable = None,
) -> list[dict]:
    """Scrape all comments from a single Instagram post/reel URL.

    Args:
        url: Instagram post or reel URL.
        cookies: Optional dict of {name: value} cookies for authentication.
        progress_callback: Optional callable(msg: str) for progress updates.

    Returns:
        List of formatted comment dicts.
    """
    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    post_url = normalize_url(url)
    shortcode = extract_shortcode(post_url)
    if not shortcode:
        _progress(f"Invalid Instagram URL: {url}")
        return []

    url_type = detect_url_type(post_url)
    if url_type == "story":
        _progress("Story URLs are not supported.")
        return []

    _progress(f"Processing: {post_url}")

    # Init session
    session, csrf_token, has_auth = await init_session(cookies)
    # Session initialized

    all_comments: list[dict] = []
    seen_ids: set[str] = set()
    media_pk = None
    parent_comments_with_replies: list[tuple[str, int]] = []

    def add_comments(comments: list[dict]):
        for c in comments:
            cid = c.get("id", "")
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                all_comments.append(c)

    try:
        # Phase 1: Fetch page HTML and extract embedded data
        _progress("Loading post...")
        html = await fetch_page_html(session, post_url)
        if not html:
            _progress("Could not load post.")
            return []

        login_page = "/accounts/login/" in html or "loginForm" in html

        web_info = None
        comments_conn = None
        shortcode_media = None

        if not login_page:
            relay_data = extract_relay_data(html)
            web_info = relay_data.get("web_info")
            comments_conn = relay_data.get("comments")
            shortcode_media = relay_data.get("shortcode_media")

        total_comment_count = 0
        has_more_comments = False
        end_cursor = None
        caption_text = ""

        # If HTML had no data (login page, or authenticated SPA shell),
        # fall back to GraphQL API which works with or without cookies.
        if not web_info and not comments_conn and not shortcode_media:
            _progress("Trying GraphQL API...")
            shortcode_media = await fetch_media_via_graphql(
                session, shortcode, csrf_token,
            )
            if not shortcode_media:
                if login_page:
                    _progress("Could not load post data. Try uploading fresh cookies.")
                else:
                    _progress(
                        "No data found. The post may be private or the format has changed."
                    )

        if web_info:
            caption_text = web_info.get("caption_text", "")

        # New format: xdt_api__v1
        if web_info:
            total_comment_count = web_info.get("comment_count", 0) or 0
            shortcode = web_info.get("code", shortcode)
            media_pk = web_info.get("pk")
            _progress(f"Found post with {total_comment_count} comments")

        if comments_conn and comments_conn.get("edges"):
            for edge in comments_conn["edges"]:
                child_count = edge.get("child_comment_count", 0) or 0
                comment_pk = edge.get("pk")
                comment = format_comment_v2(
                    {
                        "pk": comment_pk,
                        "text": edge.get("text", ""),
                        "created_at": edge.get("created_at", 0),
                        "child_comment_count": child_count,
                        "comment_like_count": edge.get("comment_like_count"),
                        "user": {
                            "username": edge.get("username", ""),
                            "pk": edge.get("user_pk", ""),
                            "is_verified": edge.get("is_verified", False),
                            "profile_pic_url": edge.get("profile_pic_url", ""),
                        },
                    },
                    post_url, url, depth=0, caption_text=caption_text,
                )
                if comment:
                    add_comments([comment])
                if child_count > 0 and comment_pk:
                    parent_comments_with_replies.append((str(comment_pk), child_count))

            has_more_comments = comments_conn.get("has_next_page", False)
            end_cursor = comments_conn.get("end_cursor")

        # Legacy format (also used by GraphQL fallback)
        elif shortcode_media:
            total_comment_count = shortcode_media.get("comment_count", 0) or 0
            media_pk = shortcode_media.get("id")
            if not caption_text:
                caption_text = shortcode_media.get("caption_text", "")
            _progress(f"Found post with {total_comment_count} comments")
            for edge in shortcode_media.get("edges", []):
                comment = format_comment_v1(
                    {
                        "id": edge.get("id"),
                        "text": edge.get("text", ""),
                        "created_at": edge.get("created_at", 0),
                        "owner": {
                            "username": edge.get("username", ""),
                            "id": edge.get("user_id", ""),
                            "is_verified": edge.get("is_verified", False),
                            "profile_pic_url": edge.get("profile_pic_url", ""),
                        },
                        "edge_liked_by": {"count": edge.get("likes", 0)},
                        "child_comment_count": edge.get("replies_count", 0),
                    },
                    post_url, url, depth=0, caption_text=caption_text,
                )
                if comment:
                    add_comments([comment])
                for reply_edge in edge.get("reply_edges", []):
                    reply = format_comment_v1(
                        {
                            "id": reply_edge.get("id"),
                            "text": reply_edge.get("text", ""),
                            "created_at": reply_edge.get("created_at", 0),
                            "owner": {
                                "username": reply_edge.get("username", ""),
                                "id": reply_edge.get("user_id", ""),
                                "is_verified": reply_edge.get("is_verified", False),
                                "profile_pic_url": reply_edge.get("profile_pic_url", ""),
                            },
                            "edge_liked_by": {"count": reply_edge.get("likes", 0)},
                        },
                        post_url, url, depth=1, caption_text=caption_text,
                    )
                    if reply:
                        add_comments([reply])

            has_more_comments = shortcode_media.get("has_next_page", False)
            end_cursor = shortcode_media.get("end_cursor")

        # Fallback: preview comments
        elif web_info and web_info.get("preview_comments"):
            for pc in web_info["preview_comments"]:
                comment = format_comment_v2(
                    {
                        "pk": pc.get("pk"),
                        "text": pc.get("text", ""),
                        "created_at": pc.get("created_at", 0),
                        "user": {
                            "username": pc.get("username", ""),
                            "pk": pc.get("user_pk", pc.get("user_id", "")),
                            "is_verified": pc.get("is_verified", False),
                            "profile_pic_url": pc.get("profile_pic_url", ""),
                        },
                    },
                    post_url, url, depth=0, caption_text=caption_text,
                )
                if comment:
                    add_comments([comment])
            has_more_comments = total_comment_count > len(all_comments)

        if all_comments:
            _progress(f"Found {len(all_comments)} comments")

        # Phase 2: Pagination
        if has_auth and media_pk:
            # Authenticated REST API pagination
            top_level_count = len(
                [c for c in all_comments if c.get("threadingDepth", 0) == 0]
            )
            if has_more_comments or top_level_count < total_comment_count:
                _progress("Loading more comments...")
                min_id = None
                consecutive_empty = 0
                page_num = 0
                while page_num < MAX_PAGES:
                    page_num += 1
                    result = await fetch_comments_rest(
                        session, str(media_pk), csrf_token, min_id,
                    )
                    if not result or result.get("__error"):
                        if result:
                            _progress("Could not load more comments")
                        break

                    comments_list = result.get("comments", [])
                    if not comments_list:
                        break

                    before = len(all_comments)
                    for c in comments_list:
                        child_count = c.get("child_comment_count", 0) or 0
                        cpk = c.get("pk")
                        comment = format_comment_v2(
                            c, post_url, url, depth=0, caption_text=caption_text,
                        )
                        if comment:
                            add_comments([comment])
                        if (
                            child_count > 0
                            and cpk
                            and (str(cpk), child_count)
                            not in parent_comments_with_replies
                        ):
                            parent_comments_with_replies.append(
                                (str(cpk), child_count)
                            )
                    added = len(all_comments) - before

                    next_min_id = result.get("next_min_id")
                    if not next_min_id or added == 0:
                        consecutive_empty += 1
                        if consecutive_empty >= 3 or not next_min_id:
                            break
                    else:
                        consecutive_empty = 0
                    min_id = next_min_id
                    _progress(f"Found {len(all_comments)} comments so far...")
                    await asyncio.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

                # Fetch child/reply comments
                if parent_comments_with_replies:
                    _progress("Loading replies...")
                    for comment_pk, child_count in parent_comments_with_replies:
                        max_id = None
                        fetched = 0
                        while fetched < child_count + 10:
                            result = await fetch_child_comments(
                                session, str(media_pk), comment_pk,
                                csrf_token, max_id,
                            )
                            if not result or result.get("__error"):
                                break

                            children = result.get("child_comments", [])
                            if not children:
                                break

                            for child in children:
                                reply = format_comment_v2(
                                    child, post_url, url, depth=1,
                                    caption_text=caption_text,
                                )
                                if reply:
                                    add_comments([reply])
                                fetched += 1

                            next_max_id = result.get("next_max_child_cursor")
                            if not next_max_id or len(children) == 0:
                                break
                            max_id = next_max_id
                            await asyncio.sleep(random.uniform(0.3, 0.8))

        elif has_more_comments and end_cursor:
            # Unauthenticated pagination
            _progress("Loading more comments...")
            captured_doc_id = None
            for test_id in GRAPHQL_DOC_IDS:
                result = await graphql_query(
                    session, test_id,
                    {"shortcode": shortcode, "first": 5},
                    csrf_token,
                )
                if result and not result.get("__error"):
                    conn = find_key_recursive(
                        result,
                        "xdt_api__v1__media__media_id__comments__connection",
                    )
                    media = find_key_recursive(result, "xdt_shortcode_media")
                    if (conn and isinstance(conn, dict)) or (
                        media and isinstance(media, dict)
                    ):
                        captured_doc_id = test_id
                        break
                await asyncio.sleep(0.5)

            if captured_doc_id:
                cursor = end_cursor
                page_num = 0
                consecutive_empty = 0
                while has_more_comments and page_num < MAX_PAGES:
                    page_num += 1
                    variables = {
                        "shortcode": shortcode,
                        "first": COMMENTS_PER_PAGE,
                    }
                    if cursor:
                        variables["after"] = cursor
                    result = await graphql_query(
                        session, captured_doc_id, variables, csrf_token,
                    )
                    if not result or result.get("__error"):
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            break
                        await asyncio.sleep(PAGE_DELAY_MAX)
                        continue

                    comments_data = find_key_recursive(
                        result,
                        "xdt_api__v1__media__media_id__comments__connection",
                    )
                    if comments_data and isinstance(comments_data, dict):
                        edges = comments_data.get("edges", [])
                        before = len(all_comments)
                        for edge in edges:
                            node = edge.get("node", edge)
                            c = format_comment_v2(
                                node, post_url, url, caption_text=caption_text,
                            )
                            if c:
                                add_comments([c])
                        added = len(all_comments) - before
                        pi = comments_data.get("page_info", {})
                        cursor = pi.get("end_cursor")
                        has_more_comments = pi.get("has_next_page", False)
                    else:
                        media = (
                            find_key_recursive(result, "xdt_shortcode_media")
                            or find_key_recursive(result, "shortcode_media")
                        )
                        if media and isinstance(media, dict):
                            ce = (
                                media.get("edge_media_to_parent_comment")
                                or media.get("edge_media_to_comment")
                            )
                            if ce and isinstance(ce, dict):
                                edges = ce.get("edges", [])
                                before = len(all_comments)
                                add_comments(
                                    extract_comments_from_edges_v1(
                                        edges, post_url, url,
                                        caption_text=caption_text,
                                    )
                                )
                                added = len(all_comments) - before
                                pi = ce.get("page_info", {})
                                cursor = pi.get("end_cursor")
                                has_more_comments = pi.get("has_next_page", False)
                            else:
                                has_more_comments = False
                                continue
                        else:
                            consecutive_empty += 1
                            if consecutive_empty >= 3:
                                break
                            await asyncio.sleep(PAGE_DELAY_MAX)
                            continue

                    if added == 0:
                        consecutive_empty += 1
                        if consecutive_empty >= 10:
                            break
                    else:
                        consecutive_empty = 0
                    _progress(f"Found {len(all_comments)} comments so far...")
                    await asyncio.sleep(
                        random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX)
                    )

    finally:
        await session.close()

    top_level = sum(1 for c in all_comments if c.get("threadingDepth", 0) == 0)
    replies = len(all_comments) - top_level
    _progress(f"Done: {len(all_comments)} comments ({top_level} top-level + {replies} replies)")

    return all_comments

# ──────────────────────────────────────────────
# Public Entry Point
# ──────────────────────────────────────────────

def _convert_cookies(cookies: list[dict] | dict | None) -> dict | None:
    """Convert Playwright-format cookies (list of dicts) to simple {name: value} dict."""
    if cookies is None:
        return None
    if isinstance(cookies, dict):
        return cookies
    result = {}
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name and value:
            result[name] = value
    return result if result else None


async def scrape_post_urls(
    urls: list[str],
    cookies: list[dict] | dict | None = None,
    progress_callback: callable = None,
) -> list[dict]:
    """Scrape Instagram comments from one or more post/reel URLs.

    Parameters
    ----------
    urls : list[str]
        Instagram post or reel URLs to scrape.
    cookies : list[dict] | dict, optional
        Playwright-format cookies (list of dicts with name/value/domain/path)
        or simple {name: value} dict. If a cookie named ``sessionid``
        is present the scraper will use authenticated REST API pagination.
    progress_callback : callable, optional
        Called with a single *str* argument for progress messages.

    Returns
    -------
    list[dict]
        All scraped comments across every URL.
    """
    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    # Convert cookies to simple dict format
    cookie_dict = _convert_cookies(cookies)

    if cookie_dict:
        has_session = "sessionid" in cookie_dict
        _progress("Cookies loaded")

    # Pre-filter invalid URLs
    valid_urls: list[str] = []
    for url in urls:
        url = url.strip()
        if not url or url.startswith("#"):
            continue
        if not extract_shortcode(url):
            _progress(f"Skipping invalid URL: {url}")
            continue
        valid_urls.append(url)

    if not valid_urls:
        _progress("No valid URLs to process.")
        return []

    all_results: list[dict] = []

    for i, url in enumerate(valid_urls):
        if len(valid_urls) > 1:
            _progress(f"--- Post {i+1}/{len(valid_urls)} ---")

        comments = await scrape_single_post(
            url, cookies=cookie_dict, progress_callback=progress_callback,
        )
        if comments:
            all_results.extend(comments)
        else:
            _progress("No comments found")

    _progress(f"Done: {len(all_results)} comments from {len(valid_urls)} posts")
    return all_results
