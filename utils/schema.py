"""
Unified schema mapper — normalizes comments from all platforms
into a clean, analysis-ready format.
"""

CLEAN_FIELDS = [
    "platform",
    "text",
    "username",
    "likes",
    "replies",
    "date",
    "is_reply",
    "source_url",
    "content_title",
    "language",
]

# Per-platform field mappings: clean_field -> raw_field
_FIELD_MAP = {
    "youtube": {
        "username": "profileName",
        "likes": "likesCount",
        "replies": "commentsCount",
        "date": "date",
        "is_reply": lambda c: _safe_int(c.get("threadingDepth", 0)) > 0,
        "source_url": "youtubeUrl",
        "content_title": "videoTitle",
        "language": None,
    },
    "tiktok": {
        "username": "username",
        "likes": "like_count",
        "replies": "reply_count",
        "date": "created_at",
        "is_reply": "is_reply",
        "source_url": "video_url",
        "content_title": "video_caption",
        "language": "language",
    },
    "facebook": {
        "username": "profileName",
        "likes": "likesCount",
        "replies": "commentsCount",
        "date": "date",
        "is_reply": lambda c: _safe_int(c.get("threadingDepth", 0)) > 0,
        "source_url": "facebookUrl",
        "content_title": "postCaption",
        "language": None,
    },
    "instagram": {
        "username": "ownerUsername",
        "likes": "likesCount",
        "replies": "repliesCount",
        "date": "date",
        "is_reply": lambda c: _safe_int(c.get("threadingDepth", 0)) > 0,
        "source_url": "instagramUrl",
        "content_title": "captionText",
        "language": None,
    },
}


def _safe_int(val) -> int:
    """Convert a value to int, handling strings like '123' or empty values."""
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        val = val.strip().replace(",", "")
        if not val:
            return 0
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0
    return 0


def normalize_comment(comment: dict, platform: str) -> dict:
    """Normalize a single comment from any platform to clean schema."""
    mapping = _FIELD_MAP.get(platform, {})
    clean = {"platform": platform}

    # Text — always "text" across all platforms
    clean["text"] = comment.get("text", "")

    for clean_field in CLEAN_FIELDS:
        if clean_field in ("platform", "text"):
            continue

        raw_key = mapping.get(clean_field)

        if raw_key is None:
            clean[clean_field] = "" if clean_field != "is_reply" else False
        elif callable(raw_key):
            clean[clean_field] = raw_key(comment)
        else:
            val = comment.get(raw_key, "")
            if clean_field in ("likes", "replies"):
                val = _safe_int(val)
            clean[clean_field] = val

    return clean


def normalize_comments(comments: list[dict], platform: str) -> list[dict]:
    """Normalize a list of comments from a given platform."""
    return [normalize_comment(c, platform) for c in comments]


def to_clean(comments: list[dict], platform: str) -> list[dict]:
    """Convert raw comments to clean (analysis-ready) format."""
    return normalize_comments(comments, platform)


def to_raw(comments: list[dict]) -> list[dict]:
    """Return raw comments as-is (passthrough)."""
    return comments
