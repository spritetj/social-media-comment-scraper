"""
Progress UI — Friendly progress panel for scraping operations.
Shows rotating fun messages, live counter, and progress bar.
No internal logs or technical details are exposed to the user.
"""

import re


# Rotating friendly messages shown during scraping
_FUN_MESSAGES = [
    "Warming up the engines...",
    "Diving into the comments...",
    "Sorting through conversations...",
    "Finding some real gems...",
    "Almost there, hang tight...",
    "Gathering the good stuff...",
    "Scooping up replies...",
    "Doing the heavy lifting...",
]


class ProgressTracker:
    """
    Parses raw scraper progress messages internally (to count comments
    and detect completion) but only shows friendly, rotating messages
    and a live counter to the user.
    """

    def __init__(self, total_videos: int, placeholder):
        self.total = total_videos
        self.placeholder = placeholder
        self.completed_videos = 0
        self.total_comments = 0
        self.msg_index = 0
        self.done = False
        self.elapsed = 0.0

        self._render()

    def on_message(self, msg: str):
        """Parse a progress callback message and update internal state."""
        msg = str(msg).strip()
        if not msg:
            return

        # Detect video/post boundary
        boundary = re.match(r"^---\s*(?:Video|Post)\s*(\d+)/(\d+)\s*---$", msg)
        if boundary:
            idx = int(boundary.group(1))
            if idx > 1:
                self.completed_videos = idx - 1
            self._advance_message()
            self._render()
            return

        # Detect count update
        count_match = re.match(r"^(?:Found|Fetched)\s+(\d+)\s+comments?", msg, re.IGNORECASE)
        if count_match:
            self._advance_message()
            self._render()
            return

        # Detect completion per video/post
        got_match = re.match(r"^Got\s+(\d+)\s+comments?", msg, re.IGNORECASE)
        if got_match:
            self.total_comments += int(got_match.group(1))
            self.completed_videos = min(self.completed_videos + 1, self.total)
            self._advance_message()
            self._render()
            return

        # Detect no comments
        if re.match(r"^No comments found", msg, re.IGNORECASE):
            self.completed_videos = min(self.completed_videos + 1, self.total)
            self._advance_message()
            self._render()
            return

        # Detect error
        if "went wrong" in msg.lower() or "error" in msg.lower():
            self._render()
            return

        # All other messages: just rotate the fun message
        self._advance_message()
        self._render()

    def complete(self, total: int, elapsed: float):
        """Mark the entire operation as complete."""
        self.done = True
        self.total_comments = total
        self.completed_videos = self.total
        self.elapsed = elapsed
        self._render()

    def _advance_message(self):
        self.msg_index = (self.msg_index + 1) % len(_FUN_MESSAGES)

    def _render(self):
        """Render the progress panel."""
        html = self._build_html()
        self.placeholder.markdown(html, unsafe_allow_html=True)

    def _build_html(self) -> str:
        progress_pct = (self.completed_videos / self.total * 100) if self.total > 0 else 0

        if self.done:
            dot_class = "prg-dot prg-dot-done"
            label = f"All done! Found {self.total_comments} comments in {self.elapsed:.1f}s"
            bar_class = "prg-bar-fill prg-bar-done"
            progress_pct = 100
        else:
            dot_class = "prg-dot prg-dot-active"
            label = _FUN_MESSAGES[self.msg_index]
            bar_class = "prg-bar-fill prg-bar-active"

        return (
            '<div class="prg-panel">'
            "<style>"
            ".prg-panel{background:#1C1C1E;border:1px solid rgba(240,238,233,0.08);"
            "border-radius:16px;padding:1.25rem 1.5rem;"
            "font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Helvetica Neue',sans-serif;"
            "margin:1rem 0}"
            ".prg-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem}"
            ".prg-header-left{display:flex;align-items:center;gap:0.5rem}"
            ".prg-dot{width:8px;height:8px;border-radius:50%;background:#48484A;display:inline-block}"
            ".prg-dot-active{background:#30D158;animation:prg-pulse 1.5s ease infinite}"
            ".prg-dot-done{background:#30D158}"
            ".prg-label{font-size:0.875rem;color:#F0EEE9;font-weight:500}"
            ".prg-counter{font-size:1.75rem;font-weight:700;color:#F0EEE9;letter-spacing:-0.02em;line-height:1}"
            ".prg-bar{height:3px;background:#2C2C2E;border-radius:2px;overflow:hidden}"
            ".prg-bar-fill{height:100%;border-radius:2px;transition:width 0.6s cubic-bezier(0.4,0,0.2,1)}"
            ".prg-bar-active{background:linear-gradient(90deg,#F0EEE9,rgba(240,238,233,0.6));"
            "animation:prg-shimmer 2s linear infinite;background-size:200% 100%}"
            ".prg-bar-done{background:#30D158}"
            "@keyframes prg-pulse{0%,100%{opacity:1}50%{opacity:0.4}}"
            "@keyframes prg-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}"
            "</style>"
            '<div class="prg-header">'
            '<div class="prg-header-left">'
            f'<span class="{dot_class}"></span>'
            f'<span class="prg-label">{label}</span>'
            "</div>"
            f'<span class="prg-counter">{self.total_comments}</span>'
            "</div>"
            '<div class="prg-bar">'
            f'<div class="{bar_class}" style="width:{progress_pct}%"></div>'
            "</div>"
            "</div>"
        )
