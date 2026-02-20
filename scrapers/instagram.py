"""
Instagram Comment Scraper -- Web App Edition
=============================================
Extracted / refactored from instagram_comment_scraper.py for use inside the
Streamlit web application.  All file I/O, Rich console output, CLI entry
points and auto-installer logic have been removed.  Results are returned as
plain ``list[dict]`` and progress is reported via an optional callback.

Two scraping strategies:
  1) PRIMARY: Extracts comments from Instagram's embedded Relay prefetch data
     (script tags with xdt_api__v1__media__media_id__comments__connection)
  2) FALLBACK: In-browser GraphQL queries for pagination
"""

import asyncio
import json
import random
import re
from datetime import datetime, timezone

from playwright.async_api import async_playwright, Route

# Shared utilities (AdaptiveDelay imported for cross-scraper consistency)
from utils.common import AdaptiveDelay  # noqa: F401

# ──────────────────────────────────────────────
# Constants & Config
# ──────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_IG_APP_ID = "936619743392459"
MAX_PAGES = 200
PAGE_DELAY_MIN = 1.0
PAGE_DELAY_MAX = 2.5
COMMENTS_PER_PAGE = 50

MAX_CONCURRENT_PAGES = 3          # Browser pages processing URLs in parallel
WORKER_DELAY_MIN = 0.3            # Min delay between URLs per worker (seconds)
WORKER_DELAY_MAX = 0.8            # Max delay between URLs per worker (seconds)

BLOCK_RESOURCE_PATTERNS = [
    "**/*.css", "**/*.woff", "**/*.woff2", "**/*.ttf", "**/*.otf",
    "**/analytics*", "**/pixel*", "**/logging_client_events*",
    "**/batch/log*", "**/tr/*",
]
BLOCK_MEDIA_PATTERNS = [
    "**/*.{mp4,webm,ogg,mp3,wav,m4a,aac,m3u8,ts}",
    "**/*.{jpg,jpeg,png,gif,webp,svg,ico}",
]

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
    # Remove tracking params
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
    """Format a comment from the new xdt_api format (XDTCommentDict)."""
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
# In-Browser GraphQL Fetch
# ──────────────────────────────────────────────

async def browser_graphql_fetch(
    page, doc_id: str, variables: dict, csrf_token: str,
) -> dict | None:
    """Execute a GraphQL query via in-browser fetch()."""
    form_data = {
        "doc_id": doc_id,
        "variables": json.dumps(variables),
    }
    try:
        result = await page.evaluate("""async (formData) => {
            const params = new URLSearchParams();
            for (const [key, value] of Object.entries(formData)) {
                if (key.startsWith('_')) continue;
                params.append(key, value);
            }
            try {
                const resp = await fetch('/graphql/query/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': formData._csrf || '',
                        'X-IG-App-ID': formData._app_id || '936619743392459',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-ASBD-ID': '129477',
                        'X-IG-WWW-Claim': '0',
                    },
                    body: params.toString(),
                    credentials: 'include',
                });
                if (!resp.ok) {
                    return { __error: true, status: resp.status };
                }
                return JSON.parse(await resp.text());
            } catch(e) {
                return { __error: true, message: e.message };
            }
        }""", {**form_data, "_csrf": csrf_token, "_app_id": DEFAULT_IG_APP_ID})
        return result
    except Exception:
        return None

# ──────────────────────────────────────────────
# REST API Comment Fetching (Authenticated)
# ──────────────────────────────────────────────

async def fetch_comments_rest_api(
    page, media_pk: str, csrf_token: str,
    min_id: str | None = None,
) -> dict | None:
    """Fetch top-level comments via REST API (requires auth cookies)."""
    params = "can_support_threading=true&permalink_enabled=false"
    if min_id:
        params += f"&min_id={min_id}"
    try:
        result = await page.evaluate("""async (args) => {
            try {
                const resp = await fetch('/api/v1/media/' + args.media_pk + '/comments/?' + args.params, {
                    method: 'GET',
                    headers: {
                        'X-CSRFToken': args.csrf,
                        'X-IG-App-ID': '936619743392459',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-ASBD-ID': '129477',
                    },
                    credentials: 'include',
                });
                if (!resp.ok) return { __error: true, status: resp.status };
                const text = await resp.text();
                try { return JSON.parse(text); }
                catch(e) { return { __error: true, message: 'Not JSON', snippet: text.substring(0, 200) }; }
            } catch(e) {
                return { __error: true, message: e.message };
            }
        }""", {"media_pk": str(media_pk), "params": params, "csrf": csrf_token})
        return result
    except Exception:
        return None


async def fetch_child_comments(
    page, media_pk: str, comment_pk: str,
    csrf_token: str, max_id: str | None = None,
) -> dict | None:
    """Fetch reply/child comments for a specific parent comment via REST API."""
    params = ""
    if max_id:
        params = f"?max_id={max_id}"
    try:
        result = await page.evaluate("""async (args) => {
            try {
                const url = '/api/v1/media/' + args.media_pk + '/comments/' +
                            args.comment_pk + '/child_comments/' + args.params;
                const resp = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'X-CSRFToken': args.csrf,
                        'X-IG-App-ID': '936619743392459',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-ASBD-ID': '129477',
                    },
                    credentials: 'include',
                });
                if (!resp.ok) return { __error: true, status: resp.status };
                const text = await resp.text();
                try { return JSON.parse(text); }
                catch(e) { return { __error: true, message: 'Not JSON', snippet: text.substring(0, 200) }; }
            } catch(e) {
                return { __error: true, message: e.message };
            }
        }""", {
            "media_pk": str(media_pk),
            "comment_pk": str(comment_pk),
            "params": params,
            "csrf": csrf_token,
        })
        return result
    except Exception:
        return None

# ──────────────────────────────────────────────
# Embedded Data Extraction (Primary Method)
# ──────────────────────────────────────────────

JS_EXTRACT_RELAY_DATA = """() => {
    function findKey(obj, targetKey, depth) {
        if (depth > 30 || !obj || typeof obj !== 'object') return null;
        if (Array.isArray(obj)) {
            for (const item of obj) {
                const r = findKey(item, targetKey, depth + 1);
                if (r) return r;
            }
        } else {
            if (targetKey in obj) return obj[targetKey];
            for (const val of Object.values(obj)) {
                const r = findKey(val, targetKey, depth + 1);
                if (r) return r;
            }
        }
        return null;
    }

    const scripts = document.querySelectorAll('script[type="application/json"]');
    const result = { web_info: null, comments: null, shortcode_media: null };

    for (const s of scripts) {
        try {
            const parsed = JSON.parse(s.textContent || '');

            // New format: xdt_api__v1__media__shortcode__web_info
            if (!result.web_info) {
                const webInfo = findKey(parsed, 'xdt_api__v1__media__shortcode__web_info', 0);
                if (webInfo && webInfo.items && webInfo.items[0]) {
                    const item = webInfo.items[0];
                    result.web_info = {
                        code: item.code,
                        pk: item.pk,
                        id: item.id,
                        comment_count: item.comment_count,
                        like_count: item.like_count,
                        username: item.user ? item.user.username : '',
                        caption_text: item.caption ? (item.caption.text || '') : '',
                        taken_at: item.taken_at,
                        media_type: item.media_type,
                        preview_comments: (item.preview_comments || []).map(function(c) {
                            return {
                                pk: c.pk, text: c.text,
                                username: c.user ? c.user.username : '',
                                user_pk: c.user ? c.user.pk : '',
                                user_id: c.user ? c.user.id : '',
                                is_verified: c.user ? c.user.is_verified : false,
                                profile_pic_url: c.user ? c.user.profile_pic_url : '',
                                created_at: c.created_at,
                            };
                        }),
                    };
                }
            }

            // New format: xdt_api__v1__media__media_id__comments__connection
            if (!result.comments) {
                const commentsConn = findKey(parsed, 'xdt_api__v1__media__media_id__comments__connection', 0);
                if (commentsConn) {
                    result.comments = {
                        edges: (commentsConn.edges || []).map(function(e) {
                            var n = e.node || {};
                            return {
                                pk: n.pk,
                                text: n.text,
                                created_at: n.created_at,
                                child_comment_count: n.child_comment_count || 0,
                                comment_like_count: n.comment_like_count,
                                username: n.user ? n.user.username : '',
                                user_pk: n.user ? (n.user.pk || n.user.id) : '',
                                is_verified: n.user ? n.user.is_verified : false,
                                profile_pic_url: n.user ? n.user.profile_pic_url : '',
                                parent_comment_id: n.parent_comment_id,
                                typename: n.__typename,
                            };
                        }),
                        has_next_page: commentsConn.page_info ? commentsConn.page_info.has_next_page : false,
                        end_cursor: commentsConn.page_info ? commentsConn.page_info.end_cursor : null,
                    };
                }
            }

            // Legacy format: xdt_shortcode_media (fallback)
            if (!result.shortcode_media) {
                var media = findKey(parsed, 'xdt_shortcode_media', 0);
                if (!media) media = findKey(parsed, 'shortcode_media', 0);
                if (media && typeof media === 'object' && media.id) {
                    var ce = media.edge_media_to_parent_comment || media.edge_media_to_comment || {};
                    result.shortcode_media = {
                        id: media.id,
                        shortcode: media.shortcode,
                        typename: media.__typename,
                        comment_count: ce.count || 0,
                        has_next_page: ce.page_info ? ce.page_info.has_next_page : false,
                        end_cursor: ce.page_info ? ce.page_info.end_cursor : null,
                        edges: (ce.edges || []).map(function(e) {
                            var n = e.node || {};
                            return {
                                id: n.id, text: n.text,
                                created_at: n.created_at,
                                username: (n.owner || n.user || {}).username || '',
                                user_id: (n.owner || n.user || {}).id || '',
                                is_verified: (n.owner || n.user || {}).is_verified || false,
                                profile_pic_url: (n.owner || n.user || {}).profile_pic_url || '',
                                likes: n.edge_liked_by ? n.edge_liked_by.count : (n.comment_like_count || 0),
                                replies_count: n.edge_threaded_comments ? n.edge_threaded_comments.count : (n.child_comment_count || 0),
                                reply_edges: n.edge_threaded_comments ? (n.edge_threaded_comments.edges || []).map(function(re) {
                                    var rn = re.node || {};
                                    return {
                                        id: rn.id, text: rn.text,
                                        created_at: rn.created_at,
                                        username: (rn.owner || rn.user || {}).username || '',
                                        user_id: (rn.owner || rn.user || {}).id || '',
                                        is_verified: (rn.owner || rn.user || {}).is_verified || false,
                                        profile_pic_url: (rn.owner || rn.user || {}).profile_pic_url || '',
                                        likes: rn.edge_liked_by ? rn.edge_liked_by.count : (rn.comment_like_count || 0),
                                    };
                                }) : [],
                            };
                        }),
                    };
                }
            }
        } catch(e) {}
    }

    return result;
}"""


JS_EXTRACT_COMMENTS_FROM_DOM = """() => {
    // Fallback: extract comments from rendered DOM elements
    const comments = [];
    const seen = new Set();

    // Method 1: Look for comment containers with username links
    const allLinks = document.querySelectorAll('a[href^="/"]');
    for (const link of allLinks) {
        const username = link.textContent.trim();
        if (!username || username.includes(' ') || username.length > 30) continue;

        // Find parent container
        const container = link.closest('li, div[role="listitem"]');
        if (!container) continue;

        // Find comment text - look for span siblings/descendants
        const spans = container.querySelectorAll('span');
        let commentText = '';
        for (const span of spans) {
            const text = span.textContent.trim();
            if (text === username) continue;
            if (text.length > 1 && text.length < 3000 &&
                !/^(View|Load|Reply|like|\\d+ (like|reply|replies|hour|min|day|week|month|year))/i.test(text)) {
                if (text.length > commentText.length) {
                    commentText = text;
                }
            }
        }

        if (commentText && username) {
            const key = username + '|' + commentText.substring(0, 50);
            if (!seen.has(key)) {
                seen.add(key);
                comments.push({
                    username: username,
                    text: commentText,
                    href: link.getAttribute('href'),
                });
            }
        }
    }
    return comments;
}"""

# ──────────────────────────────────────────────
# Core Scraper
# ──────────────────────────────────────────────

async def scrape_single_post(
    page, post_url: str, input_url: str,
    csrf_token: str, has_auth: bool = False,
    progress_callback: callable = None,
) -> list[dict]:
    """Scrape comments from a single post using an existing browser page."""

    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    post_url = normalize_url(post_url)
    shortcode = extract_shortcode(post_url)
    if not shortcode:
        return []

    url_type = detect_url_type(post_url)
    if url_type == "story":
        return []

    all_comments = []
    seen_ids = set()
    media_pk = None  # numeric media ID for REST API

    def add_comments(comments: list[dict]):
        for c in comments:
            cid = c.get("id", "")
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                all_comments.append(c)

    # Navigate to the post
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector(
                'script[type="application/json"]', timeout=5000,
            )
        except Exception:
            await page.wait_for_timeout(1000)  # fallback: 1 s instead of 3 s
    except Exception as e:
        _progress(f"Navigation failed: {e}")
        return []

    # Check for login wall
    if "/accounts/login/" in page.url:
        _progress("Login required")
        return []

    # Extract embedded Relay data
    try:
        relay_data = await page.evaluate(JS_EXTRACT_RELAY_DATA)
    except Exception:
        relay_data = {}

    if not relay_data:
        return []

    web_info = relay_data.get("web_info")
    comments_conn = relay_data.get("comments")
    shortcode_media = relay_data.get("shortcode_media")
    total_comment_count = 0
    has_more_comments = False
    end_cursor = None
    # Track parent comments that have replies (for child comment fetching)
    parent_comments_with_replies: list[tuple[str, int]] = []

    # -- Extract caption text --
    caption_text = ""
    if web_info:
        caption_text = web_info.get("caption_text", "")

    # -- New format: xdt_api__v1 --
    if web_info:
        total_comment_count = web_info.get("comment_count", 0) or 0
        shortcode = web_info.get("code", shortcode)
        media_pk = web_info.get("pk")

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
                post_url, input_url, depth=0, caption_text=caption_text,
            )
            if comment:
                add_comments([comment])
            if child_count > 0 and comment_pk:
                parent_comments_with_replies.append(
                    (str(comment_pk), child_count)
                )

        has_more_comments = comments_conn.get("has_next_page", False)
        end_cursor = comments_conn.get("end_cursor")

    # -- Legacy format: xdt_shortcode_media --
    elif shortcode_media:
        total_comment_count = shortcode_media.get("comment_count", 0) or 0
        media_pk = shortcode_media.get("id")
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
                post_url, input_url, depth=0, caption_text=caption_text,
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
                    post_url, input_url, depth=1, caption_text=caption_text,
                )
                if reply:
                    add_comments([reply])

        has_more_comments = shortcode_media.get("has_next_page", False)
        end_cursor = shortcode_media.get("end_cursor")

    # -- Fallback: preview comments from web_info --
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
                post_url, input_url, depth=0, caption_text=caption_text,
            )
            if comment:
                add_comments([comment])
        has_more_comments = total_comment_count > len(all_comments)

    # -- DOM fallback if nothing found --
    if not all_comments:
        try:
            dom_comments = await page.evaluate(JS_EXTRACT_COMMENTS_FROM_DOM)
            for i, dc in enumerate(dom_comments):
                add_comments([{
                    "instagramUrl": post_url,
                    "id": f"dom_{i}",
                    "text": dc.get("text", ""),
                    "date": "",
                    "timestamp": 0,
                    "ownerUsername": dc.get("username", ""),
                    "ownerId": "",
                    "ownerIsVerified": False,
                    "ownerProfilePicUrl": "",
                    "likesCount": 0,
                    "repliesCount": 0,
                    "threadingDepth": 0,
                    "inputUrl": input_url,
                    "captionText": caption_text,
                }])
        except Exception:
            pass

    # ──────────────────────────────────────────
    # Authenticated: Paginate all comments via REST API
    # ──────────────────────────────────────────
    if has_auth and media_pk:
        top_level_count = len(
            [c for c in all_comments if c.get("threadingDepth", 0) == 0]
        )
        if has_more_comments or top_level_count < total_comment_count:
            _progress(
                f"Fetching remaining comments via API "
                f"({top_level_count}/{total_comment_count})..."
            )
            min_id = None
            consecutive_empty = 0
            page_num = 0
            while page_num < MAX_PAGES:
                page_num += 1
                result = await fetch_comments_rest_api(
                    page, str(media_pk), csrf_token, min_id,
                )
                if not result or result.get("__error"):
                    if result:
                        _progress(
                            f"API error: "
                            f"{result.get('status', result.get('message', 'unknown'))}"
                        )
                    break

                comments_list = result.get("comments", [])
                if not comments_list:
                    break

                before = len(all_comments)
                for c in comments_list:
                    child_count = c.get("child_comment_count", 0) or 0
                    cpk = c.get("pk")
                    comment = format_comment_v2(
                        c, post_url, input_url, depth=0,
                        caption_text=caption_text,
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

                # Check pagination
                next_min_id = result.get("next_min_id")
                if not next_min_id or added == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 3 or not next_min_id:
                        break
                else:
                    consecutive_empty = 0
                min_id = next_min_id
                await asyncio.sleep(
                    random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX)
                )

        # -- Fetch child/reply comments --
        if parent_comments_with_replies:
            total_replies = sum(
                cnt for _, cnt in parent_comments_with_replies
            )
            _progress(
                f"Fetching replies for "
                f"{len(parent_comments_with_replies)} comments "
                f"({total_replies} replies)..."
            )
            for comment_pk, child_count in parent_comments_with_replies:
                max_id = None
                fetched = 0
                while fetched < child_count + 10:  # small buffer
                    result = await fetch_child_comments(
                        page, str(media_pk), comment_pk, csrf_token, max_id,
                    )
                    if not result or result.get("__error"):
                        break

                    children = result.get("child_comments", [])
                    if not children:
                        break

                    for child in children:
                        reply = format_comment_v2(
                            child, post_url, input_url, depth=1,
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

    # -- Fallback pagination via GraphQL (no auth) --
    elif has_more_comments and end_cursor:
        known_doc_ids = [
            "8845758582119845",
            "7803498539768460",
            "9064463823609386",
        ]
        captured_doc_id = None
        for test_id in known_doc_ids:
            result = await browser_graphql_fetch(
                page, test_id,
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
                result = await browser_graphql_fetch(
                    page, captured_doc_id, variables, csrf_token,
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
                            node, post_url, input_url,
                            caption_text=caption_text,
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
                                    edges, post_url, input_url,
                                    caption_text=caption_text,
                                )
                            )
                            added = len(all_comments) - before
                            pi = ce.get("page_info", {})
                            cursor = pi.get("end_cursor")
                            has_more_comments = pi.get(
                                "has_next_page", False,
                            )
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
                await asyncio.sleep(
                    random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX)
                )

    return all_comments

# ──────────────────────────────────────────────
# Worker Helpers
# ──────────────────────────────────────────────

async def _setup_worker_page(context):
    """Create a new page with media blocking routes."""
    page = await context.new_page()

    async def block_media(route: Route):
        await route.abort()

    for pattern in BLOCK_MEDIA_PATTERNS:
        await page.route(pattern, block_media)
    return page


async def _url_worker(
    worker_id: int, page, url_queue: asyncio.Queue,
    results: list, results_lock: asyncio.Lock,
    progress: dict, csrf_token: str, has_auth: bool,
    total_urls: int, progress_callback: callable = None,
):
    """Queue-based worker that processes URLs from a shared queue."""

    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    while True:
        try:
            url = url_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        progress["done"] += 1
        current = progress["done"]
        _progress(
            f"Processing {current}/{total_urls} (worker {worker_id}): {url}"
        )

        try:
            comments = await scrape_single_post(
                page, url, url, csrf_token, has_auth,
                progress_callback=progress_callback,
            )
            if comments:
                async with results_lock:
                    results.extend(comments)
                _progress(
                    f"{len(comments)} comments (worker {worker_id})"
                )
            else:
                _progress(f"No comments found (worker {worker_id})")
        except Exception as e:
            _progress(f"Error on worker {worker_id}: {e}")
            try:
                await page.goto("about:blank", timeout=5000)
            except Exception:
                pass

        # Anti-detection delay between URLs
        if not url_queue.empty():
            await asyncio.sleep(
                random.uniform(WORKER_DELAY_MIN, WORKER_DELAY_MAX)
            )

# ──────────────────────────────────────────────
# Public Entry Point
# ──────────────────────────────────────────────

async def scrape_post_urls(
    urls: list[str],
    cookies: list[dict] | None = None,
    progress_callback: callable = None,
) -> list[dict]:
    """Scrape Instagram comments from one or more post/reel URLs.

    Parameters
    ----------
    urls : list[str]
        Instagram post or reel URLs to scrape.
    cookies : list[dict], optional
        Playwright-format cookies (list of dicts with at least ``name``,
        ``value``, ``domain``, ``path``).  If a cookie named ``sessionid``
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

    all_results: list[dict] = []

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

    # Launch browser
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
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

    # Context-level blocking for CSS, fonts, and tracking
    async def block_resource(route: Route):
        await route.abort()

    for pattern in BLOCK_RESOURCE_PATTERNS:
        await context.route(pattern, block_resource)

    # Load cookies if provided
    has_auth = False
    if cookies:
        await context.add_cookies(cookies)
        has_auth = any(c.get("name") == "sessionid" for c in cookies)
        if has_auth:
            _progress("Authenticated session (cookies loaded)")
        else:
            _progress("Cookies loaded but no sessionid found")

    # Establish session with a temporary setup page
    setup_page = await _setup_worker_page(context)
    _progress("Establishing session...")
    try:
        await setup_page.goto(
            "https://www.instagram.com/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await setup_page.wait_for_timeout(2000)
        try:
            await setup_page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    const text = btn.textContent || '';
                    if (text.includes('Allow') || text.includes('Accept') ||
                        text.includes('essential') || text.includes('Decline')) {
                        btn.click(); break;
                    }
                }
            }""")
        except Exception:
            pass
    except Exception as e:
        _progress(f"Session warning: {e}")

    # Get CSRF token
    csrf_token = ""
    for c in await context.cookies():
        if c["name"] == "csrftoken":
            csrf_token = c["value"]
            break

    # Close setup page -- cookies are shared via context
    await setup_page.close()

    # Create worker pages
    num_workers = min(len(valid_urls), MAX_CONCURRENT_PAGES)
    worker_pages = []
    for _ in range(num_workers):
        worker_pages.append(await _setup_worker_page(context))

    _progress(
        f"Launching {num_workers} worker(s) for {len(valid_urls)} URLs..."
    )

    # Fill queue
    url_queue: asyncio.Queue[str] = asyncio.Queue()
    for url in valid_urls:
        url_queue.put_nowait(url)

    # Launch workers
    results_lock = asyncio.Lock()
    progress_state = {"done": 0}
    worker_tasks = [
        _url_worker(
            i, worker_pages[i], url_queue, all_results, results_lock,
            progress_state, csrf_token, has_auth, len(valid_urls),
            progress_callback=progress_callback,
        )
        for i in range(num_workers)
    ]
    await asyncio.gather(*worker_tasks)

    # Cleanup
    for wp in worker_pages:
        try:
            await wp.close()
        except Exception:
            pass
    await browser.close()
    await pw.stop()

    _progress(
        f"Done: {len(all_results)} comments from {len(valid_urls)} posts"
    )
    return all_results
