"""
NotebookLM Comment Export
==========================
Formats scraped comments as structured markdown optimized for
NotebookLM ingestion. Groups by platform with metadata for
cross-platform analysis.

NotebookLM limits: ~500K words per source, 50 sources per notebook.
"""

from datetime import datetime


def export_comments_markdown(
    comments: list[dict],
    topic: str,
    platforms: list[str] | None = None,
) -> str:
    """Format comments as a structured markdown document for NotebookLM.

    Args:
        comments: Normalized comment dicts (clean schema).
        topic: The search topic.
        platforms: Platform list for header. Auto-detected if None.

    Returns:
        Markdown string ready for download/upload to NotebookLM.
    """
    if not comments:
        return f"# Social Media Comments: {topic}\n\nNo comments collected.\n"

    # Group by platform
    by_platform: dict[str, list[dict]] = {}
    for c in comments:
        p = c.get("platform", "unknown")
        by_platform.setdefault(p, []).append(c)

    if platforms is None:
        platforms = sorted(by_platform.keys())

    # Detect date range
    dates = []
    for c in comments:
        d = c.get("date", "")
        if d and isinstance(d, str) and len(d) >= 10:
            dates.append(d[:10])
    date_range = ""
    if dates:
        dates.sort()
        date_range = f"{dates[0]} to {dates[-1]}"

    # Build markdown
    lines = [
        f"# Social Media Comments: {topic}",
        "",
        "## Collection Summary",
        f"- **Total comments:** {len(comments):,}",
        f"- **Platforms:** {', '.join(p.title() for p in platforms)}",
    ]
    if date_range:
        lines.append(f"- **Date range:** {date_range}")
    lines.append(f"- **Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Per-platform sections
    for platform in platforms:
        platform_comments = by_platform.get(platform, [])
        if not platform_comments:
            continue

        lines.append(f"## {platform.title()} Comments ({len(platform_comments):,})")
        lines.append("")

        # Sort: top-level comments first, then by likes descending
        top_level = [c for c in platform_comments if not c.get("is_reply")]
        replies = [c for c in platform_comments if c.get("is_reply")]
        top_level.sort(key=lambda c: c.get("likes", 0), reverse=True)

        # Build reply lookup by parent
        reply_map: dict[str, list[dict]] = {}
        for r in replies:
            parent = r.get("parent_id", "")
            if parent:
                reply_map.setdefault(parent, []).append(r)

        comment_num = 0
        for c in top_level:
            comment_num += 1
            _append_comment(lines, c, comment_num)

            # Append replies
            comment_id = c.get("comment_id", "")
            if comment_id and comment_id in reply_map:
                for reply in reply_map[comment_id]:
                    _append_reply(lines, reply)

        # Orphan replies (no matching parent in top-level)
        used_reply_ids = set()
        for reply_list in reply_map.values():
            for r in reply_list:
                used_reply_ids.add(id(r))
        for r in replies:
            if id(r) not in used_reply_ids:
                comment_num += 1
                _append_comment(lines, r, comment_num, is_orphan_reply=True)

        lines.append("")

    return "\n".join(lines)


def _append_comment(
    lines: list[str], c: dict, num: int, is_orphan_reply: bool = False
):
    """Append a formatted comment line."""
    text = c.get("text", "").strip()
    if not text:
        return

    username = c.get("username", "Anonymous")
    likes = c.get("likes", 0)
    date = c.get("date", "")

    meta_parts = []
    if likes:
        meta_parts.append(f"{likes} likes")
    if date:
        meta_parts.append(str(date)[:10] if len(str(date)) >= 10 else str(date))
    meta = f" ({', '.join(meta_parts)})" if meta_parts else ""

    prefix = "[Reply] " if is_orphan_reply else ""
    lines.append(f"{num}. {prefix}@{username}{meta}: \"{text}\"")


def _append_reply(lines: list[str], c: dict):
    """Append a formatted reply line (indented)."""
    text = c.get("text", "").strip()
    if not text:
        return

    username = c.get("username", "Anonymous")
    likes = c.get("likes", 0)

    meta = f" ({likes} likes)" if likes else ""
    lines.append(f"   [Reply] @{username}{meta}: \"{text}\"")


def estimate_word_count(comments: list[dict]) -> int:
    """Estimate total word count for NotebookLM limit checking."""
    total = 0
    for c in comments:
        text = c.get("text", "")
        total += len(text.split())
        # Account for metadata overhead (~10 words per comment)
        total += 10
    return total


def split_for_notebooklm(
    comments: list[dict],
    topic: str,
    max_words: int = 450_000,
) -> list[str]:
    """Split comments into multiple markdown files if too large.

    Args:
        comments: All comments.
        topic: Search topic.
        max_words: Max words per file (default 450K, below 500K limit).

    Returns:
        List of markdown strings (usually just one).
    """
    total_words = estimate_word_count(comments)
    if total_words <= max_words:
        return [export_comments_markdown(comments, topic)]

    # Split into chunks
    chunks = []
    current_chunk: list[dict] = []
    current_words = 0

    for c in comments:
        c_words = len(c.get("text", "").split()) + 10
        if current_words + c_words > max_words and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_words = 0
        current_chunk.append(c)
        current_words += c_words

    if current_chunk:
        chunks.append(current_chunk)

    results = []
    for i, chunk in enumerate(chunks, 1):
        part_topic = f"{topic} (Part {i}/{len(chunks)})"
        results.append(export_comments_markdown(chunk, part_topic))

    return results
