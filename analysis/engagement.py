"""
Engagement metrics and statistics.
"""


def analyze_engagement(comments: list[dict]) -> dict:
    """Calculate engagement statistics from clean comments.

    Returns:
        {
            "total_comments": int,
            "total_replies": int,
            "reply_rate": float (percentage),
            "total_likes": int,
            "avg_likes": float,
            "max_likes": int,
            "engagement_score": float,
            "top_liked": [top 10 most liked comments],
            "top_replied": [top 10 most replied-to comments],
            "most_active_users": [(username, count), ...],
        }
    """
    if not comments:
        return {}

    total = len(comments)
    replies = [c for c in comments if c.get("is_reply")]
    top_level = [c for c in comments if not c.get("is_reply")]
    reply_count = len(replies)

    likes = [c.get("likes", 0) or 0 for c in comments]
    total_likes = sum(likes)
    avg_likes = total_likes / total if total else 0
    max_likes = max(likes) if likes else 0

    reply_rate = (reply_count / total * 100) if total else 0

    # Engagement score: weighted combination of volume, likes, and reply activity
    engagement_score = min(100, (total * 0.3 + total_likes * 0.05 + reply_count * 0.5))

    # Top liked comments
    sorted_by_likes = sorted(comments, key=lambda c: c.get("likes", 0) or 0, reverse=True)
    top_liked = [
        {
            "text": c.get("text", "")[:200],
            "username": c.get("username", ""),
            "likes": c.get("likes", 0),
        }
        for c in sorted_by_likes[:10]
    ]

    # Top replied-to comments (top-level only, by reply count)
    sorted_by_replies = sorted(
        top_level,
        key=lambda c: c.get("replies", 0) or 0,
        reverse=True,
    )
    top_replied = [
        {
            "text": c.get("text", "")[:200],
            "username": c.get("username", ""),
            "replies": c.get("replies", 0),
        }
        for c in sorted_by_replies[:10]
    ]

    # Most active users
    from collections import Counter
    user_counts = Counter(c.get("username", "unknown") for c in comments)
    most_active = user_counts.most_common(10)

    return {
        "total_comments": total,
        "total_replies": reply_count,
        "reply_rate": round(reply_rate, 1),
        "total_likes": total_likes,
        "avg_likes": round(avg_likes, 1),
        "max_likes": max_likes,
        "engagement_score": round(engagement_score, 1),
        "top_liked": top_liked,
        "top_replied": top_replied,
        "most_active_users": most_active,
    }
