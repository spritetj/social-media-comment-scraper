"""
Facebook Comments Scraper -- FAST Edition (In-Browser GraphQL API)
==================================================================
Refactored for Streamlit web app. No CLI, no file I/O, no Rich console.

Instead of scrolling through a browser for 3+ minutes, this:
  1. Loads the page ONCE in a headless browser (~5s) to capture tokens
  2. Keeps the browser open (no scrolling/rendering)
  3. Fires fetch() calls FROM INSIDE the browser to Facebook's GraphQL API
  4. Paginates via cursors -- no scrolling, no rendering overhead

The key insight: Python `requests` gets blocked by Facebook's TLS fingerprinting,
but fetch() calls from within the browser share the full session state and pass
all anti-bot checks.

Typically 5-15x faster than browser-scroll method.
"""

import asyncio
import base64
import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs

from playwright.async_api import async_playwright

from utils.common import AdaptiveDelay

logging.getLogger("playwright").setLevel(logging.ERROR)


# ==============================================================================
#  CONSTANTS
# ==============================================================================

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Known doc_ids for Facebook comment queries
DOC_ID_ROOT = "25750071871314498"       # CommentListComponentsRootQuery
DOC_ID_PAGINATION = "26362559876663565"  # CommentsListComponentsPaginationQuery
DOC_ID_REPLIES = "25549931698036634"    # Depth1CommentsListPaginationQuery


# ==============================================================================
#  URL DETECTION & ID EXTRACTION
# ==============================================================================

def detect_url_type(url: str) -> str:
    """Detect whether a URL is a regular post, reel, watch/video, or photo."""
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
    """Extract numeric post/reel/video ID from a Facebook URL."""
    patterns = [
        r'/reel/(\d+)',
        r'[?&]v=(\d+)',
        r'fbid=(\d+)',
        r'story_fbid=(\d+)',
        r'/posts/[^/]+/(\d+)',
        r'/videos/[^/]+/(\d+)',
        r'(?:posts|videos|photos)/(\d+)',
        r'/(\d{10,})(?:[/?]|$)',  # Fallback: any 10+ digit number at end
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return ""


def build_feedback_id(post_id: str) -> str:
    """Construct a base64-encoded feedback_id from a numeric post ID."""
    raw = f"feedback:{post_id}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


# ==============================================================================
#  HELPERS
# ==============================================================================

def decode_fb_id(b64_id: str) -> str:
    try:
        return base64.b64decode(b64_id).decode("utf-8")
    except Exception:
        return b64_id


def format_timestamp(ts) -> str:
    try:
        if isinstance(ts, (int, float)) and ts > 0:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        pass
    return str(ts) if ts else ""


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


def _is_comment(obj: dict) -> bool:
    body = obj.get("body")
    if not isinstance(body, dict) or "text" not in body:
        return False
    author = obj.get("author")
    if not isinstance(author, dict) or "name" not in author:
        return False
    return "created_time" in obj


def find_end_cursor(data, depth=0) -> str:
    """Find the pagination end_cursor for the main comments list."""
    if depth > 20:
        return ""
    if isinstance(data, dict):
        # Look for the comments connection with page_info (NOT replies_connection)
        comments_conn = data.get("comments")
        if isinstance(comments_conn, dict):
            pi = comments_conn.get("page_info")
            if isinstance(pi, dict) and pi.get("end_cursor") and pi.get("has_next_page"):
                return pi["end_cursor"]

        # Also check comment_rendering_instance_for_feed_location
        cri = data.get("comment_rendering_instance_for_feed_location")
        if isinstance(cri, dict):
            result = find_end_cursor(cri, depth + 1)
            if result:
                return result

        # Generic: look for page_info but skip replies_connection
        for key, value in data.items():
            if key in ("replies_connection", "replies_fields"):
                continue  # Skip reply pagination
            result = find_end_cursor(value, depth + 1)
            if result:
                return result

    elif isinstance(data, list):
        for item in data:
            result = find_end_cursor(item, depth + 1)
            if result:
                return result
    return ""


def find_post_caption(data, feedback_id: str = "", depth: int = 0) -> tuple[str, int]:
    """
    Find the post caption (message.text) in parsed JSON data.
    Returns (caption_text, priority) where priority:
      3 = feedback.id matches our post's feedback_id
      2 = node has a feedback sibling (it's a post/story)
      1 = node has Story/Post typename
      0 = not found
    """
    if depth > 25:
        return "", 0
    if isinstance(data, dict):
        tn = data.get("__typename", "")
        if tn == "Comment":
            return "", 0  # Skip comment subtrees

        best_caption = ""
        best_priority = 0

        # Check if this node has message.text
        message = data.get("message")
        if isinstance(message, dict) and isinstance(message.get("text"), str) and message["text"]:
            feedback = data.get("feedback")
            has_feedback = isinstance(feedback, dict) and feedback.get("id")

            if has_feedback and feedback_id and feedback["id"] == feedback_id:
                return message["text"], 3  # Exact match -- return immediately
            elif has_feedback:
                best_caption = message["text"]
                best_priority = 2
            elif "Story" in tn or "Post" in tn:
                best_caption = message["text"]
                best_priority = 1

        # Recurse into children
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


def find_expansion_tokens(data, tokens: dict, depth=0):
    """
    Find expansion_token values in GraphQL data.
    Returns dict mapping feedback_id -> expansion_token.
    Handles multiple structures:
      - {"expansion_token": "...", "id": "..."}
      - {"id": "...", "expansion_info": {"expansion_token": "..."}}
    """
    if depth > 30:
        return
    if isinstance(data, dict):
        # Structure 1: expansion_token directly on the dict
        exp_token = data.get("expansion_token")
        if exp_token and isinstance(exp_token, str):
            fid = data.get("id", "")
            if not fid:
                feedback = data.get("feedback")
                if isinstance(feedback, dict):
                    fid = feedback.get("id", "")
            if fid:
                tokens[fid] = exp_token

        # Structure 2: expansion_info.expansion_token (common in API responses)
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


def format_comment(node: dict, post_url: str, input_url: str, post_caption: str = "") -> dict:
    """Format a raw comment node to Apify-compatible output."""
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


# ==============================================================================
#  IN-BROWSER GRAPHQL FETCH
# ==============================================================================

async def browser_graphql_fetch(page, form_data: dict) -> str:
    """
    Execute a fetch() call from INSIDE the browser to Facebook's GraphQL API.
    This bypasses TLS fingerprinting and shares the full browser session.
    Returns the raw response text.
    """
    # Build URL-encoded form data string in JS
    js_code = """
    async (formData) => {
        const params = new URLSearchParams();
        for (const [key, value] of Object.entries(formData)) {
            if (value !== null && value !== undefined) {
                params.append(key, String(value));
            }
        }
        try {
            const resp = await fetch('/api/graphql/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-FB-Friendly-Name': formData.fb_api_req_friendly_name || '',
                    'X-FB-LSD': formData.lsd || '',
                    'X-ASBD-ID': '359341',
                },
                body: params.toString(),
                credentials: 'include',
            });
            return await resp.text();
        } catch (e) {
            return JSON.stringify({error: e.message});
        }
    }
    """
    try:
        result = await page.evaluate(js_code, form_data)
        return result or ""
    except Exception as e:
        return json.dumps({"error": str(e)})


async def browser_graphql_fetch_batch(page, form_data_list: list[dict]) -> list[str]:
    """
    Execute multiple fetch() calls in parallel from INSIDE the browser via Promise.all().
    This is much faster than sequential page.evaluate() calls since Playwright serializes
    evaluate calls via CDP -- batching into a single evaluate with Promise.all() enables
    true parallel network requests.
    Returns a list of raw response texts (same order as input).
    """
    js_code = """
    async (requests) => {
        const results = await Promise.all(requests.map(async (formData) => {
            const params = new URLSearchParams();
            for (const [key, value] of Object.entries(formData)) {
                if (value !== null && value !== undefined) {
                    params.append(key, String(value));
                }
            }
            try {
                const resp = await fetch('/api/graphql/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-FB-Friendly-Name': formData.fb_api_req_friendly_name || '',
                        'X-FB-LSD': formData.lsd || '',
                        'X-ASBD-ID': '359341',
                    },
                    body: params.toString(),
                    credentials: 'include',
                });
                return await resp.text();
            } catch (e) {
                return JSON.stringify({error: e.message});
            }
        }));
        return results;
    }
    """
    try:
        results = await page.evaluate(js_code, form_data_list)
        return results or [""] * len(form_data_list)
    except Exception as e:
        return [json.dumps({"error": str(e)})] * len(form_data_list)


def parse_graphql_response(text: str) -> tuple[list[dict], str]:
    """Parse a GraphQL response into (comment_nodes, next_cursor)."""
    if text.startswith("for (;;);"):
        text = text[9:]

    comments = []
    next_cursor = ""
    json_objects = []

    # Try as single JSON first, then multi-line
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
    """Extract expansion tokens from a raw GraphQL response text.
    Returns dict mapping feedback_id -> expansion_token."""
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


# ==============================================================================
#  PHASE 1: Browser -- load page, extract tokens (one-time, ~8 seconds)
# ==============================================================================

async def setup_browser_and_extract_tokens(
    post_url: str, cookies: list[dict],
    browser=None, pw=None,
    progress_fn=None,
) -> dict:
    """
    Load the page once in a browser to extract tokens and capture
    the GraphQL request template. Returns tokens + the live page object.

    If browser/pw are provided, reuses them (creates a new context only).
    Otherwise launches a new browser.
    """
    def _progress(msg):
        if progress_fn:
            progress_fn(msg)

    url_type = detect_url_type(post_url)
    owns_browser = browser is None  # Track if we launched the browser ourselves

    # Pre-compute URL-based post ID -- used as a HINT, not gospel truth
    # For photo.php URLs, fbid is the media ID (unreliable as post feedback_id)
    url_post_id = extract_post_id_from_url(post_url)
    url_id_reliable = url_type not in ("photo",)  # photo fbid != post feedback_id

    result = {
        "fb_dtsg": "",
        "lsd": "",
        "jazoest": "",
        "user_id": "",
        "feedback_id": "",
        "initial_comments": [],
        "initial_cursor": "",
        "canonical_url": "",
        "template_params": {},
        "doc_id_pagination": DOC_ID_PAGINATION,
        "doc_id_root": DOC_ID_ROOT,
        "doc_id_replies": DOC_ID_REPLIES,
        "expansion_tokens": {},  # feedback_id -> expansion_token
        "feed_location": "",  # Captured from actual traffic, or inferred from URL type
        "post_caption": "",
        "url_type": url_type,
        "owns_browser": owns_browser,
        # These stay alive for Phase 2:
        "page": None,
        "browser": None,
        "pw": None,
    }

    if not pw:
        pw = await async_playwright().start()
    try:
        if not browser:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--metrics-recording-only",
                    "--no-first-run",
                ],
            )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        # Block heavy resources via CDP for zero-overhead interception
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Network.setBlockedURLs", {"urls": [
            "*.mp4", "*.webm", "*.ogg", "*.mp3", "*.wav", "*.m4a", "*.m3u8", "*.ts",
            "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.svg", "*.ico",
            "*.woff", "*.woff2", "*.ttf", "*.eot",
            "**/ajax/bz*", "**/ajax/mercury*",
        ]})
        await cdp.send("Network.enable")

        # Capture GraphQL request templates from browser traffic
        captured_template = {}

        async def handle_request(route, request):
            if "/api/graphql/" in request.url and request.method == "POST":
                post_data = request.post_data or ""
                params = parse_qs(post_data)
                friendly = params.get("fb_api_req_friendly_name", [""])[0]

                # Capture feedLocation from any comment-related query
                if "comment" in friendly.lower() or "Comment" in friendly:
                    try:
                        vj = json.loads(params.get("variables", ["{}"])[0])
                        fl = vj.get("feedLocation", "")
                        if fl and not result["feed_location"]:
                            result["feed_location"] = fl
                    except Exception:
                        pass

                if friendly == "CommentsListComponentsPaginationQuery" and not captured_template:
                    captured_template.update(
                        {k: v[0] if len(v) == 1 else v for k, v in params.items()}
                    )
                    result["doc_id_pagination"] = params.get("doc_id", [DOC_ID_PAGINATION])[0]
                    try:
                        vj = json.loads(params.get("variables", ["{}"])[0])
                        if vj.get("id"):
                            result["feedback_id"] = vj["id"]
                    except Exception:
                        pass

                if friendly == "CommentListComponentsRootQuery":
                    result["doc_id_root"] = params.get("doc_id", [DOC_ID_ROOT])[0]
                    try:
                        vj = json.loads(params.get("variables", ["{}"])[0])
                        # Accept if no feedback_id yet, or override unverified one
                        if vj.get("id") and (not result["feedback_id"] or not feedback_id_verified):
                            result["feedback_id"] = vj["id"]
                    except Exception:
                        pass

                if friendly == "Depth1CommentsListPaginationQuery":
                    result["doc_id_replies"] = params.get("doc_id", [DOC_ID_REPLIES])[0]

                # Capture feedback_id and feedLocation from ANY comment query
                # (reels/watch may use different friendly names)
                if (not result["feedback_id"] or not feedback_id_verified) and ("comment" in friendly.lower() or "Comment" in friendly):
                    try:
                        vj = json.loads(params.get("variables", ["{}"])[0])
                        fid = vj.get("id", "") or vj.get("feedbackID", "") or vj.get("feedback_id", "")
                        if fid:
                            result["feedback_id"] = fid
                    except Exception:
                        pass

            await route.continue_()

        await page.route("**/api/graphql/**", handle_request)

        # Navigate -- use "commit" for fastest start, then wait for needed content
        await page.goto(post_url, wait_until="commit", timeout=60000)
        try:
            await page.wait_for_selector('script[type="application/json"]', timeout=10000)
        except Exception:
            # Fallback: short fixed wait if no JSON scripts found quickly
            await page.wait_for_timeout(500)

        result["canonical_url"] = page.url

        # Re-detect URL type from final URL (page may redirect, e.g. /posts/ -> /reel/)
        # Keep both original and canonical post IDs as candidates
        canonical_post_id = extract_post_id_from_url(page.url)
        candidate_post_ids = set()
        if url_post_id:
            candidate_post_ids.add(url_post_id)
        if canonical_post_id:
            candidate_post_ids.add(canonical_post_id)

        final_url_type = detect_url_type(page.url)
        if final_url_type != url_type:
            _progress(f"URL redirected: {url_type} -> {final_url_type} ({page.url[:80]})")
            url_type = final_url_type
            result["url_type"] = url_type
            url_id_reliable = final_url_type not in ("photo",)

        # Extract tokens from page scripts
        tokens = await page.evaluate("""() => {
            var r = {};
            var scripts = document.querySelectorAll('script');
            for (var i = 0; i < scripts.length; i++) {
                var t = scripts[i].textContent;
                if (!r.fb_dtsg) {
                    var m = t.match(/"DTSGInitialData".*?"token":"([^"]+)"/);
                    if (m) r.fb_dtsg = m[1];
                }
                if (!r.fb_dtsg) {
                    var m2 = t.match(/fb_dtsg.*?value":"([^"]+)"/);
                    if (m2) r.fb_dtsg = m2[1];
                }
                if (!r.lsd) {
                    var m3 = t.match(/"LSD".*?"token":"([^"]+)"/);
                    if (m3) r.lsd = m3[1];
                }
                if (!r.jazoest) {
                    var m4 = t.match(/jazoest[=:]([0-9]+)/);
                    if (m4) r.jazoest = m4[1];
                }
            }
            var dtsgInput = document.querySelector('input[name="fb_dtsg"]');
            if (dtsgInput && !r.fb_dtsg) r.fb_dtsg = dtsgInput.value;
            var lsdInput = document.querySelector('input[name="lsd"]');
            if (lsdInput && !r.lsd) r.lsd = lsdInput.value;
            return r;
        }""")
        result["fb_dtsg"] = tokens.get("fb_dtsg", "")
        result["lsd"] = tokens.get("lsd", "")
        result["jazoest"] = tokens.get("jazoest", "")

        # Get user_id from cookies
        for c in cookies:
            if c["name"] == "c_user":
                result["user_id"] = c["value"]
                break

        # Extract feedback_id, initial comments, and expansion tokens from embedded scripts
        # (single JS call iterates all scripts once -- avoids redundant page.evaluate calls)
        script_data = await page.evaluate("""() => {
            var r = {scripts: [], feedback_ids: [], expansion_tokens: {}};
            var scripts = document.querySelectorAll('script[type="application/json"]');
            for (var i = 0; i < scripts.length; i++) {
                var t = scripts[i].textContent;
                if (t.includes('"Comment"') && t.includes('"body"')) {
                    r.scripts.push(t);
                }
                // Pattern 1: "feedback_id":"..." (standard posts)
                var matches = t.match(/"feedback_id":"([^"]+)"/g);
                if (matches) {
                    for (var j = 0; j < matches.length; j++) {
                        var id = matches[j].match(/"feedback_id":"([^"]+)"/)[1];
                        if (r.feedback_ids.indexOf(id) === -1) r.feedback_ids.push(id);
                    }
                }
                // Pattern 2: "feedback":{"id":"..."} (reels/watch/video)
                // These are base64-encoded feedback IDs like ZmVlZGJhY2s6...
                var matches2 = t.match(/"feedback":\\s*\\{\\s*"id":\\s*"([A-Za-z0-9+/=]+)"/g);
                if (matches2) {
                    for (var j = 0; j < matches2.length; j++) {
                        var m = matches2[j].match(/"id":\\s*"([A-Za-z0-9+/=]+)"/);
                        if (m) {
                            var id = m[1];
                            // Verify it's a feedback ID by checking base64 decode starts with "feedback:"
                            try {
                                var decoded = atob(id);
                                if (decoded.startsWith('feedback:') && r.feedback_ids.indexOf(id) === -1) {
                                    r.feedback_ids.push(id);
                                }
                            } catch(e) {}
                        }
                    }
                }
                // Expansion tokens: regex-based extraction (fast, no JSON.parse)
                var re = /"expansion_token":"([^"]+)"/g;
                var em;
                while ((em = re.exec(t)) !== null) {
                    var token = em[1];
                    var before = t.substring(Math.max(0, em.index - 500), em.index);
                    var idMatch = before.match(/"id":"([A-Za-z0-9+/=]+)"/g);
                    if (idMatch) {
                        var lastId = idMatch[idMatch.length - 1].match(/"id":"([^"]+)"/)[1];
                        r.expansion_tokens[lastId] = token;
                    }
                }
            }
            return r;
        }""")

        # Find the main post's feedback_id using layered strategy:
        #   1. URL match against extracted feedback_ids (highest confidence)
        #   2. Route-captured feedback_id from traffic (already set above)
        #   3. Heuristic: pick the one with most reply children
        #   4. Construct from URL (last resort, only when no other option)
        all_fids = script_data.get("feedback_ids", [])
        decoded_fids = [(fid, decode_fb_id(fid)) for fid in all_fids]
        feedback_id_verified = False  # True when matched against URL

        # Strategy 1: URL match -- try all candidate IDs (only when reliable)
        if url_id_reliable and candidate_post_ids:
            for pid in candidate_post_ids:
                for fid, decoded in decoded_fids:
                    if decoded == f"feedback:{pid}":
                        result["feedback_id"] = fid
                        feedback_id_verified = True
                        break
                if feedback_id_verified:
                    break

        # Strategy 2: Route-captured (already in result["feedback_id"] from traffic)
        # URL match takes priority if found
        if feedback_id_verified:
            pass  # URL match wins
        elif result["feedback_id"]:
            pass  # Keep route-captured as-is

        # Strategy 3: Heuristic -- pick feedback_id with most reply children
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

        # Strategy 4: Construct from URL -- only for regular posts (NOT reel/watch/video)
        # For reel/watch/video, the correct feedback_id comes from opening the comment
        # panel, which triggers GraphQL traffic captured by the route handler below.
        if not result["feedback_id"] and url_post_id and url_type == "post":
            result["feedback_id"] = build_feedback_id(url_post_id)
            _progress(f"Constructed feedback_id from URL: feedback:{url_post_id}")

        # Parse initial comments, expansion tokens, AND caption from embedded data
        # (reuses already-parsed JSON -- no extra page.evaluate needed for caption)
        comment_ids = set()
        caption_priority = 0
        for text in script_data.get("scripts", []):
            try:
                data = json.loads(text)
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
                # Also extract expansion tokens for reply fetching
                find_expansion_tokens(data, result["expansion_tokens"])
                # Extract post caption from same parsed data (zero extra cost)
                cap_text, cap_pri = find_post_caption(data, result["feedback_id"])
                if cap_pri > caption_priority:
                    result["post_caption"] = cap_text
                    caption_priority = cap_pri
            except Exception:
                pass

        # Filter initial_comments -- only when feedback_id was verified against URL
        # (avoids dropping real comments when feedback_id source is uncertain)
        if feedback_id_verified and result["feedback_id"] and result["initial_comments"]:
            target_decoded = decode_fb_id(result["feedback_id"])
            filtered = []
            for node in result["initial_comments"]:
                fb = node.get("feedback", {})
                if isinstance(fb, dict) and fb.get("id"):
                    decoded_cid = decode_fb_id(fb["id"])
                    if decoded_cid.startswith(target_decoded):
                        filtered.append(node)
                        continue
                else:
                    filtered.append(node)
            if len(filtered) != len(result["initial_comments"]):
                dropped = len(result["initial_comments"]) - len(filtered)
                _progress(f"Filtered out {dropped} comments from other posts")
                result["initial_comments"] = filtered
                comment_ids = {n.get("id", "") for n in filtered if n.get("id")}

        # Merge expansion tokens extracted via regex in the JS call above
        js_exp_tokens = script_data.get("expansion_tokens", {})
        if js_exp_tokens:
            result["expansion_tokens"].update(js_exp_tokens)

        # Fallback caption: og:description meta tag (fast, no JSON parsing)
        if not result["post_caption"]:
            og_desc = await page.evaluate(
                '() => { var m = document.querySelector("meta[property=\\"og:description\\"]"); return m ? m.content : ""; }'
            )
            if og_desc:
                result["post_caption"] = og_desc
                caption_priority = -1  # mark as fallback

        if result["post_caption"]:
            source = "embedded_json" if caption_priority > 0 else "og_meta"
            preview = result["post_caption"][:80] + ("..." if len(result["post_caption"]) > 80 else "")
            _progress(f"Post caption ({source}, p{caption_priority}): {preview}")

        # Close popups that might interfere
        await page.evaluate("""() => {
            document.querySelectorAll('[role="dialog"]').forEach(el => {
                var t = el.textContent || '';
                if ((t.includes('Log in') || t.includes('Create new account'))
                    && el.querySelectorAll('[role="article"]').length === 0) el.remove();
            });
            document.querySelectorAll('[data-nosnippet]').forEach(el => el.remove());
            document.body.style.overflow = 'auto';
        }""")

        # For reel/watch/video: click the comment icon to open comment panel
        if url_type in ("reel", "watch", "video"):
            _progress(f"Detected {url_type} URL -- opening comment panel...")
            comment_panel_opened = False

            # Strategy 1: Click comment icon (speech bubble) via aria-label
            for label in ["Comment", "Comments", "comment", "Leave a comment"]:
                try:
                    btn = page.locator(f'[aria-label="{label}"]').first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        # Wait for comment articles to appear instead of fixed wait
                        try:
                            await page.wait_for_selector('[role="article"]', timeout=3000)
                        except Exception:
                            await page.wait_for_timeout(300)
                        comment_panel_opened = True
                        _progress(f"Opened comments via [{label}] button")
                        break
                except Exception:
                    continue

            # Strategy 2: Look for comment count text and click it
            if not comment_panel_opened:
                for pattern in ["comments", "comment", "Comments"]:
                    try:
                        # Match "123 comments" or "1 comment" text
                        btn = page.locator(f'span:has-text("{pattern}")').first
                        if await btn.is_visible(timeout=1500):
                            parent = btn.locator("xpath=ancestor::div[@role='button']").first
                            if await parent.is_visible(timeout=500):
                                await parent.click()
                            else:
                                await btn.click()
                            # Wait for comment articles to appear instead of fixed wait
                            try:
                                await page.wait_for_selector('[role="article"]', timeout=3000)
                            except Exception:
                                await page.wait_for_timeout(300)
                            comment_panel_opened = True
                            _progress("Opened comments via comment count text")
                            break
                    except Exception:
                        continue

            # Strategy 3: For reels, look for the comment icon in the action bar
            if not comment_panel_opened:
                try:
                    # Reels have a vertical action bar with icons; comment icon is usually SVG-based
                    opened = await page.evaluate("""() => {
                        // Look for clickable elements near comment-related text
                        var all = document.querySelectorAll('[role="button"]');
                        for (var i = 0; i < all.length; i++) {
                            var t = (all[i].textContent || '').trim().toLowerCase();
                            var label = (all[i].getAttribute('aria-label') || '').toLowerCase();
                            if (label.includes('comment') || (t.match(/^\\d+$/) && all[i].querySelector('svg'))) {
                                // Could be the comment count button with just a number + icon
                                continue;
                            }
                        }
                        // Also try finding comment section directly -- it might already be open
                        var articles = document.querySelectorAll('[role="article"]');
                        return articles.length > 0;
                    }""")
                    if opened:
                        comment_panel_opened = True
                except Exception:
                    pass

            if not comment_panel_opened:
                _progress("Could not find comment button -- comments may already be visible")

            # Wait for comments to load after opening panel
            if not comment_panel_opened:
                # Panel wasn't explicitly opened; wait briefly for any lazy-loaded scripts
                await page.wait_for_timeout(300)
            # else: already waited for [role="article"] above

            # Re-extract from embedded scripts after panel opened
            # (comments might now be loaded that weren't before)
            extra_data = await page.evaluate("""() => {
                var r = {scripts: [], feedback_ids: []};
                var scripts = document.querySelectorAll('script[type="application/json"]');
                for (var i = 0; i < scripts.length; i++) {
                    var t = scripts[i].textContent;
                    if (t.includes('"Comment"') && t.includes('"body"')) {
                        r.scripts.push(t);
                    }
                    // Pattern 1: "feedback_id":"..."
                    var matches = t.match(/"feedback_id":"([^"]+)"/g);
                    if (matches) {
                        for (var j = 0; j < matches.length; j++) {
                            var id = matches[j].match(/"feedback_id":"([^"]+)"/)[1];
                            if (r.feedback_ids.indexOf(id) === -1) r.feedback_ids.push(id);
                        }
                    }
                    // Pattern 2: "feedback":{"id":"..."} (reels/watch)
                    var matches2 = t.match(/"feedback":\\s*\\{\\s*"id":\\s*"([A-Za-z0-9+/=]+)"/g);
                    if (matches2) {
                        for (var j = 0; j < matches2.length; j++) {
                            var m = matches2[j].match(/"id":\\s*"([A-Za-z0-9+/=]+)"/);
                            if (m) {
                                try {
                                    var decoded = atob(m[1]);
                                    if (decoded.startsWith('feedback:') && r.feedback_ids.indexOf(m[1]) === -1) {
                                        r.feedback_ids.push(m[1]);
                                    }
                                } catch(e) {}
                            }
                        }
                    }
                }
                return r;
            }""")

            # Update feedback_id if we didn't have one -- same layered strategy
            if not result["feedback_id"]:
                extra_fids = extra_data.get("feedback_ids", [])
                extra_decoded = [(fid, decode_fb_id(fid)) for fid in extra_fids]

                # Try URL match with all candidate IDs
                if url_id_reliable and candidate_post_ids:
                    for pid in candidate_post_ids:
                        for fid, decoded in extra_decoded:
                            if decoded == f"feedback:{pid}":
                                result["feedback_id"] = fid
                                feedback_id_verified = True
                                break
                        if feedback_id_verified:
                            break

                # Heuristic fallback
                if not result["feedback_id"]:
                    top_level = [(fid, d) for fid, d in extra_decoded
                                 if d.startswith("feedback:") and "_" not in d]
                    if top_level:
                        best_fid = ""
                        best_count = 0
                        for fid, decoded in top_level:
                            prefix = decoded + "_"
                            count = sum(1 for _, d in extra_decoded if d.startswith(prefix))
                            if count > best_count:
                                best_count = count
                                best_fid = fid
                        result["feedback_id"] = best_fid or top_level[0][0]
                    elif extra_fids:
                        result["feedback_id"] = extra_fids[0]

                # Construct from URL -- try all candidates as last resort
                if not result["feedback_id"] and candidate_post_ids:
                    pid = list(candidate_post_ids)[0]
                    result["feedback_id"] = build_feedback_id(pid)
                    _progress(f"Constructed feedback_id from URL: feedback:{pid}")

            # Parse extra comments from newly available scripts
            for text in extra_data.get("scripts", []):
                try:
                    data = json.loads(text)
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
                    # Also try caption from newly available scripts
                    if not result["post_caption"]:
                        cap_text, cap_pri = find_post_caption(data, result["feedback_id"])
                        if cap_text:
                            result["post_caption"] = cap_text
                            preview = cap_text[:80] + ("..." if len(cap_text) > 80 else "")
                            _progress(f"Post caption (embedded_json, after panel, p{cap_pri}): {preview}")
                except Exception:
                    pass

            # Filter extra comments -- only when feedback_id was verified
            if feedback_id_verified and result["feedback_id"] and result["initial_comments"]:
                target_decoded = decode_fb_id(result["feedback_id"])
                filtered = []
                for node in result["initial_comments"]:
                    fb = node.get("feedback", {})
                    if isinstance(fb, dict) and fb.get("id"):
                        decoded_cid = decode_fb_id(fb["id"])
                        if decoded_cid.startswith(target_decoded):
                            filtered.append(node)
                            continue
                    else:
                        filtered.append(node)
                if len(filtered) != len(result["initial_comments"]):
                    dropped = len(result["initial_comments"]) - len(filtered)
                    _progress(f"Filtered out {dropped} comments from other posts (after panel)")
                    result["initial_comments"] = filtered
                    comment_ids = {n.get("id", "") for n in filtered if n.get("id")}

        # OPTIMIZATION: Skip sort-change UI entirely.
        # Phase 2's fetch_root_comments() fires the same CommentListComponentsRootQuery
        # that sorting to "All comments" would trigger, saving ~6-8s of UI interaction.

        if captured_template:
            result["template_params"] = captured_template
            # Extract feedLocation from captured template variables (most reliable source)
            if not result["feed_location"]:
                try:
                    tvars = json.loads(captured_template.get("variables", "{}"))
                    fl = tvars.get("feedLocation", "")
                    if fl:
                        result["feed_location"] = fl
                except Exception:
                    pass

        # Disable the route interceptor so our fetch() calls go through normally
        await page.unroute("**/api/graphql/**")

        # Keep page/browser alive for Phase 2
        result["page"] = page
        result["browser"] = browser
        result["pw"] = pw

    except Exception as e:
        _progress(f"Browser error: {e}")
        if owns_browser:
            try:
                await pw.stop()
            except Exception:
                pass

    return result


# ==============================================================================
#  PHASE 2: In-Browser GraphQL API calls (the fast part!)
# ==============================================================================

async def fetch_comments_via_api(
    page,
    fb_dtsg: str,
    lsd: str,
    user_id: str,
    feedback_id: str,
    doc_id: str,
    cursor: str = None,
    template: dict = None,
    feed_location: str = "",
) -> tuple[str, list[dict], str]:
    """
    Make a single GraphQL API call via in-browser fetch().
    Returns (raw_response_text, comment_nodes, next_cursor).
    """
    variables = {
        "commentsAfterCount": -1,
        "commentsAfterCursor": cursor,
        "commentsBeforeCount": None,
        "commentsBeforeCursor": None,
        "commentsIntentToken": "REVERSE_CHRONOLOGICAL_UNFILTERED_INTENT_V1",
        "feedLocation": feed_location or "POST_PERMALINK_DIALOG",
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": feedback_id,
        "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
        "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
        "__relay_internal__pv__IsWorkUserrelayprovider": False,
    }

    form_data = {
        "av": user_id,
        "__user": user_id,
        "__a": "1",
        "fb_dtsg": fb_dtsg,
        "lsd": lsd,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "CommentsListComponentsPaginationQuery",
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": doc_id,
    }

    # Merge in extra template fields captured from the browser
    if template:
        for key in ["__aaid", "__hs", "dpr", "__ccg", "__rev", "__s", "__hsi",
                     "__dyn", "__csr", "__comet_req", "jazoest", "__spin_r",
                     "__spin_b", "__spin_t", "__crn", "__hsdp", "__hblp", "__sjsp"]:
            if key in template and key not in form_data:
                form_data[key] = template[key]

    raw_text = await browser_graphql_fetch(page, form_data)
    comments, next_cursor = parse_graphql_response(raw_text)
    return raw_text, comments, next_cursor


async def fetch_root_comments(
    page,
    fb_dtsg: str,
    lsd: str,
    user_id: str,
    feedback_id: str,
    doc_id: str,
    template: dict = None,
    feed_location: str = "",
) -> tuple[str, list[dict], str]:
    """Make the initial root comment query (like changing sort to All Comments)."""
    variables = {
        "commentsIntentToken": "REVERSE_CHRONOLOGICAL_UNFILTERED_INTENT_V1",
        "feedLocation": feed_location or "POST_PERMALINK_DIALOG",
        "feedbackSource": 2,
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": feedback_id,
        "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
        "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
        "__relay_internal__pv__IsWorkUserrelayprovider": False,
    }

    form_data = {
        "av": user_id,
        "__user": user_id,
        "__a": "1",
        "fb_dtsg": fb_dtsg,
        "lsd": lsd,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "CommentListComponentsRootQuery",
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": doc_id,
    }

    if template:
        for key in ["__aaid", "__hs", "dpr", "__ccg", "__rev", "__s", "__hsi",
                     "__dyn", "__csr", "__comet_req", "jazoest", "__spin_r",
                     "__spin_b", "__spin_t", "__crn", "__hsdp", "__hblp", "__sjsp"]:
            if key in template and key not in form_data:
                form_data[key] = template[key]

    raw_text = await browser_graphql_fetch(page, form_data)
    comments, next_cursor = parse_graphql_response(raw_text)
    return raw_text, comments, next_cursor


async def fetch_replies_for_comment(
    page,
    fb_dtsg: str,
    lsd: str,
    user_id: str,
    feedback_id: str,
    expansion_token: str,
    doc_id_replies: str,
    template: dict = None,
    feed_location: str = "",
) -> tuple[str, list[dict], str]:
    """
    Fetch replies for a single comment using Depth1CommentsListPaginationQuery.
    Uses expansion_token to identify the reply thread.
    Returns (raw_text, reply_nodes, next_cursor).
    """
    variables = {
        "clientKey": None,
        "expansionToken": expansion_token,
        "feedLocation": feed_location or "POST_PERMALINK_DIALOG",
        "focusCommentID": None,
        "repliesAfterCount": None,
        "repliesAfterCursor": None,
        "repliesBeforeCount": None,
        "repliesBeforeCursor": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": feedback_id,
        "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
        "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
        "__relay_internal__pv__IsWorkUserrelayprovider": False,
    }

    form_data = {
        "av": user_id,
        "__user": user_id,
        "__a": "1",
        "fb_dtsg": fb_dtsg,
        "lsd": lsd,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "Depth1CommentsListPaginationQuery",
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": doc_id_replies,
    }

    if template:
        for key in ["__aaid", "__hs", "dpr", "__ccg", "__rev", "__s", "__hsi",
                     "__dyn", "__csr", "__comet_req", "jazoest", "__spin_r",
                     "__spin_b", "__spin_t", "__crn", "__hsdp", "__hblp", "__sjsp"]:
            if key in template and key not in form_data:
                form_data[key] = template[key]

    raw_text = await browser_graphql_fetch(page, form_data)
    comments, next_cursor = parse_graphql_response(raw_text)
    return raw_text, comments, next_cursor


async def fetch_replies_batch(
    page,
    fb_dtsg: str,
    lsd: str,
    user_id: str,
    batch: list[dict],
    doc_id_replies: str,
    template: dict = None,
    feed_location: str = "",
) -> list[tuple[str, list[dict]]]:
    """
    Fetch replies for multiple comments in a single page.evaluate() via Promise.all().
    Each item in batch should have 'feedback_id' and 'expansion_token'.
    Returns list of (raw_text, reply_nodes) tuples.
    """
    form_data_list = []
    for item in batch:
        variables = {
            "clientKey": None,
            "expansionToken": item["expansion_token"],
            "feedLocation": feed_location or "POST_PERMALINK_DIALOG",
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
            "av": user_id,
            "__user": user_id,
            "__a": "1",
            "fb_dtsg": fb_dtsg,
            "lsd": lsd,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": "Depth1CommentsListPaginationQuery",
            "server_timestamps": "true",
            "variables": json.dumps(variables),
            "doc_id": doc_id_replies,
        }
        if template:
            for key in ["__aaid", "__hs", "dpr", "__ccg", "__rev", "__s", "__hsi",
                         "__dyn", "__csr", "__comet_req", "jazoest", "__spin_r",
                         "__spin_b", "__spin_t", "__crn", "__hsdp", "__hblp", "__sjsp"]:
                if key in template and key not in form_data:
                    form_data[key] = template[key]
        form_data_list.append(form_data)

    raw_texts = await browser_graphql_fetch_batch(page, form_data_list)

    results = []
    for raw_text in raw_texts:
        comments, _ = parse_graphql_response(raw_text)
        results.append((raw_text, comments))
    return results


# ==============================================================================
#  MAIN SCRAPING FLOW
# ==============================================================================

async def scrape_comments_fast(
    post_url: str,
    cookies: list[dict] = None,
    browser=None, pw=None,
    progress_callback: callable = None,
) -> list[dict]:
    """Scrape all comments from a post using in-browser GraphQL API method.

    Args:
        post_url: The Facebook post URL to scrape.
        cookies: List of cookie dicts (Playwright format) for authentication.
        browser: Optional shared Playwright browser instance.
        pw: Optional shared Playwright instance.
        progress_callback: Optional callable(msg: str) for progress updates.

    Returns:
        List of formatted comment dicts.
    """
    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    if cookies is None:
        cookies = []

    start_time = time.time()

    _progress("Phase 1: Loading page to capture tokens...")
    phase1_start = time.time()

    tokens = await setup_browser_and_extract_tokens(
        post_url, cookies, browser=browser, pw=pw, progress_fn=_progress,
    )

    phase1_time = time.time() - phase1_start
    _progress(f"Page loaded in {phase1_time:.1f}s")

    page = tokens.get("page")
    browser = tokens.get("browser")
    pw = tokens.get("pw")

    owns_browser = tokens.get("owns_browser", True)

    if not page or not tokens["fb_dtsg"]:
        _progress("Failed to extract tokens. Cannot proceed.")
        if page:
            try:
                await page.context.close()
            except Exception:
                pass
        if owns_browser:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass
        return []

    if not tokens["feedback_id"]:
        # Last-resort fallback: try canonical URL (page may have redirected)
        canonical = tokens.get("canonical_url", "")
        if canonical and canonical != post_url:
            pid = extract_post_id_from_url(canonical)
            if pid:
                tokens["feedback_id"] = build_feedback_id(pid)
                _progress(f"Constructed feedback_id from canonical URL: feedback:{pid}")

    if not tokens["feedback_id"]:
        _progress("Failed to find feedback_id for this post.")
        if page:
            try:
                await page.context.close()
            except Exception:
                pass
        if owns_browser:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass
        return []

    _progress(f"URL type: {tokens.get('url_type', 'post')}")
    _progress(f"fb_dtsg: {tokens['fb_dtsg'][:20]}...")
    _progress(f"feedback_id: {decode_fb_id(tokens['feedback_id'])}")
    _progress(f"feed_location: {tokens.get('feed_location', '') or 'not captured (will use default)'}")
    _progress(f"Initial comments from page: {len(tokens['initial_comments'])}")
    _progress(f"Template captured: {'yes' if tokens['template_params'] else 'no'}")

    # Collect all comments
    comment_ids = set()
    all_comments = []

    for node in tokens["initial_comments"]:
        cid = node.get("id", "")
        if cid and cid not in comment_ids:
            comment_ids.add(cid)
            all_comments.append(node)

    template = tokens["template_params"]
    expansion_tokens = dict(tokens.get("expansion_tokens", {}))

    # Resolve feed_location: prefer captured from traffic, then infer from URL type
    feed_location = tokens.get("feed_location", "")
    if not feed_location:
        url_type = tokens.get("url_type", "post")
        if url_type in ("reel", "watch", "video"):
            # Try common video/reel feed locations
            feed_location = "DEDICATED_COMMENTING_SURFACE"
        else:
            feed_location = "POST_PERMALINK_DIALOG"
        _progress(f"Using inferred feed_location: {feed_location}")

    # Phase 2+3: Paginate top-level comments + pipeline reply fetching (overlapped)
    _progress("Phase 2: Fetching comments via in-browser GraphQL API...")
    phase2_start = time.time()

    # Timing stats for diagnostics
    api_stats = {"pagination_calls": 0, "pagination_ms": 0.0,
                 "reply_calls": 0, "reply_ms": 0.0, "comments_per_page": []}
    pagination_delay = AdaptiveDelay(min_delay=0.05, max_delay=3.0, initial=0.15)

    try:
        # Step 1: Root query (like switching sort to "All comments")
        t0 = time.time()
        raw_root, root_comments, cursor = await fetch_root_comments(
            page,
            tokens["fb_dtsg"],
            tokens["lsd"],
            tokens["user_id"],
            tokens["feedback_id"],
            tokens["doc_id_root"],
            template,
            feed_location=feed_location,
        )
        api_stats["pagination_calls"] += 1
        api_stats["pagination_ms"] += (time.time() - t0) * 1000

        for node in root_comments:
            cid = node.get("id", "")
            if cid and cid not in comment_ids:
                comment_ids.add(cid)
                all_comments.append(node)

        # Collect expansion tokens from root response
        root_tokens = parse_expansion_tokens_from_text(raw_root)
        expansion_tokens.update(root_tokens)

        _progress(f"Root query: {len(root_comments)} comments, cursor: {'yes' if cursor else 'no'}")

        # If root query returned 0 comments and we're on a reel/watch/video,
        # retry with alternative feedLocation values
        url_type = tokens.get("url_type", "post")
        if not root_comments and not cursor and url_type in ("reel", "watch", "video"):
            alt_locations = [
                "DEDICATED_COMMENTING_SURFACE",
                "VIDEO_PERMALINK",
                "TAHOE",
                "POST_PERMALINK_DIALOG",
                "POST_PERMALINK_VIEW",
            ]
            # Remove the one we already tried
            alt_locations = [fl for fl in alt_locations if fl != feed_location]
            for alt_fl in alt_locations:
                _progress(f"Retrying root query with feedLocation={alt_fl}")
                t0 = time.time()
                raw_root2, root_comments2, cursor2 = await fetch_root_comments(
                    page,
                    tokens["fb_dtsg"],
                    tokens["lsd"],
                    tokens["user_id"],
                    tokens["feedback_id"],
                    tokens["doc_id_root"],
                    template,
                    feed_location=alt_fl,
                )
                api_stats["pagination_calls"] += 1
                api_stats["pagination_ms"] += (time.time() - t0) * 1000
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
                    _progress(f"Success with feedLocation={alt_fl}: {len(root_comments2)} comments")
                    break
                await asyncio.sleep(0.05)

        # Debug: if no cursor and few comments, print response size
        if not cursor and len(all_comments) < 20:
            _progress(f"Root response size: {len(raw_root)} bytes")

        # If no cursor from root query, try from initial data
        if not cursor:
            cursor = tokens.get("initial_cursor", "")
            if cursor:
                _progress("Using initial cursor from page data")

        # Step 2: Paginate top-level + pipeline reply fetches (overlapped)
        page_num = 0
        max_pages = 200
        consecutive_empty = 0

        # Reply pipelining state
        reply_tasks = []          # asyncio.Task objects for overlapping reply fetches
        pending_reply_items = []  # Accumulated reply items waiting for dispatch
        fetched_feedback_ids = set()
        REPLY_BATCH_SIZE = 10    # Concurrent fetches per Promise.all() call
        PAGES_PER_DISPATCH = 5   # Dispatch reply batch every N pagination pages
        pages_since_dispatch = 0

        def _collect_reply_items(comments_list):
            """Find comments with replies that haven't been fetched yet."""
            items = []
            for node in comments_list:
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
                            items.append({
                                "feedback_id": cfid,
                                "expansion_token": exp_token,
                                "reply_count": reply_count,
                            })
                            fetched_feedback_ids.add(cfid)
            return items

        async def _reply_batch_task(items):
            """Async task: fetch replies for a list of items (runs overlapped with pagination)."""
            results = []
            for batch_start in range(0, len(items), REPLY_BATCH_SIZE):
                batch = items[batch_start:batch_start + REPLY_BATCH_SIZE]
                t0 = time.time()
                batch_results = await fetch_replies_batch(
                    page, tokens["fb_dtsg"], tokens["lsd"], tokens["user_id"],
                    batch, tokens["doc_id_replies"], template, feed_location=feed_location,
                )
                elapsed = (time.time() - t0) * 1000
                api_stats["reply_calls"] += len(batch)
                api_stats["reply_ms"] += elapsed
                results.extend(batch_results)
            return results

        # Collect reply items from initial + root comments
        pending_reply_items.extend(_collect_reply_items(all_comments))

        while cursor and page_num < max_pages:
            page_num += 1

            t0 = time.time()
            raw_text, page_comments, next_cursor = await fetch_comments_via_api(
                page,
                tokens["fb_dtsg"],
                tokens["lsd"],
                tokens["user_id"],
                tokens["feedback_id"],
                tokens["doc_id_pagination"],
                cursor=cursor,
                template=template,
                feed_location=feed_location,
            )
            elapsed = (time.time() - t0) * 1000
            api_stats["pagination_calls"] += 1
            api_stats["pagination_ms"] += elapsed
            api_stats["comments_per_page"].append(len(page_comments))

            new_count = 0
            for node in page_comments:
                cid = node.get("id", "")
                if cid and cid not in comment_ids:
                    comment_ids.add(cid)
                    all_comments.append(node)
                    new_count += 1

            # Collect expansion tokens from this page
            page_tokens = parse_expansion_tokens_from_text(raw_text)
            expansion_tokens.update(page_tokens)

            # Find new reply items from this page's comments
            pending_reply_items.extend(_collect_reply_items(page_comments))
            pages_since_dispatch += 1

            if new_count > 0:
                _progress(f"Page {page_num}: +{new_count} comments (total: {len(all_comments)})")
                consecutive_empty = 0
                pagination_delay.on_success()
            else:
                consecutive_empty += 1
                pagination_delay.on_error()
                if consecutive_empty >= 3:
                    _progress("3 consecutive empty pages, stopping.")
                    break

            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            # Dispatch reply batch every PAGES_PER_DISPATCH pages (overlapped with pagination)
            if pages_since_dispatch >= PAGES_PER_DISPATCH and pending_reply_items:
                task = asyncio.create_task(_reply_batch_task(pending_reply_items[:]))
                reply_tasks.append(task)
                _progress(f"Dispatched {len(pending_reply_items)} reply threads (overlapped)")
                pending_reply_items = []
                pages_since_dispatch = 0

            await pagination_delay.wait()

        phase2_time = time.time() - phase2_start
        _progress(f"Top-level pagination done in {phase2_time:.1f}s ({page_num} pages)")
        _progress(f"Top-level comments: {len(all_comments)}")

        # Dispatch any remaining pending reply items
        if pending_reply_items:
            task = asyncio.create_task(_reply_batch_task(pending_reply_items[:]))
            reply_tasks.append(task)
            _progress(f"Dispatched final {len(pending_reply_items)} reply threads")
            pending_reply_items = []

        # Phase 3: Await overlapping reply tasks + deeper passes
        _progress("Phase 3: Expanding reply threads...")
        phase3_start = time.time()
        reply_count_before = len(all_comments)

        # Await all overlapping reply tasks from Phase 2
        for task in reply_tasks:
            try:
                batch_results = await task
            except Exception as e:
                _progress(f"Reply task error: {e}")
                continue
            for raw_reply, reply_nodes in batch_results:
                reply_exp_tokens = parse_expansion_tokens_from_text(raw_reply)
                expansion_tokens.update(reply_exp_tokens)
                for node in reply_nodes:
                    cid = node.get("id", "")
                    if cid and cid not in comment_ids:
                        comment_ids.add(cid)
                        all_comments.append(node)

        overlapped_replies = len(all_comments) - reply_count_before
        if overlapped_replies > 0:
            _progress(f"Overlapped reply fetch: +{overlapped_replies} replies (total: {len(all_comments)})")

        # Deeper passes (replies-to-replies, etc.)
        max_depth_passes = 5
        for depth_pass in range(max_depth_passes):
            depth_items = _collect_reply_items(all_comments)
            if not depth_items:
                break

            _progress(f"Depth pass {depth_pass + 2}: {len(depth_items)} threads to expand")

            pass_new = 0
            for batch_start in range(0, len(depth_items), REPLY_BATCH_SIZE):
                batch = depth_items[batch_start:batch_start + REPLY_BATCH_SIZE]
                t0 = time.time()
                batch_results = await fetch_replies_batch(
                    page, tokens["fb_dtsg"], tokens["lsd"], tokens["user_id"],
                    batch, tokens["doc_id_replies"], template, feed_location=feed_location,
                )
                elapsed = (time.time() - t0) * 1000
                api_stats["reply_calls"] += len(batch)
                api_stats["reply_ms"] += elapsed

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
                _progress(f"Depth pass {depth_pass + 2}: +{pass_new} nested replies (total: {len(all_comments)})")
            else:
                break

        phase3_time = time.time() - phase3_start
        new_replies_total = len(all_comments) - reply_count_before
        if new_replies_total > 0:
            _progress(f"Reply expansion: +{new_replies_total} replies in {phase3_time:.1f}s ({api_stats['reply_calls']} API calls)")
        else:
            _progress(f"No additional replies found ({api_stats['reply_calls']} API calls tried)")

        # Timing summary
        _progress("=== Timing Summary ===")
        _progress(f"Phase 1 (browser): {phase1_time:.1f}s")
        _progress(f"Phase 2 (pagination): {phase2_time:.1f}s -- {api_stats['pagination_calls']} calls, avg {api_stats['pagination_ms']/max(api_stats['pagination_calls'],1):.0f}ms/call")
        _progress(f"Phase 3 (replies): {phase3_time:.1f}s -- {api_stats['reply_calls']} calls, avg {api_stats['reply_ms']/max(api_stats['reply_calls'],1):.0f}ms/call")
        if api_stats["comments_per_page"]:
            avg_per_page = sum(api_stats["comments_per_page"]) / len(api_stats["comments_per_page"])
            _progress(f"Avg comments/page: {avg_per_page:.1f}")

    finally:
        # Close context (page's browser context), not the shared browser
        try:
            if page:
                ctx = page.context
                await ctx.close()
        except Exception:
            pass
        # Only close browser/pw if we own them (weren't passed in)
        owns_browser = tokens.get("owns_browser", True)
        if owns_browser:
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

    # Format results
    formatted = []
    canonical_url = tokens.get("canonical_url", post_url)
    post_caption = tokens.get("post_caption", "")
    for node in all_comments:
        formatted.append(format_comment(node, canonical_url, post_url, post_caption=post_caption))

    total_time = time.time() - start_time
    top_level = sum(1 for c in formatted if c.get("threadingDepth", 0) == 0)
    replies = len(formatted) - top_level

    _progress(f"Total: {len(formatted)} comments ({top_level} top-level + {replies} replies) in {total_time:.1f}s")

    return formatted
