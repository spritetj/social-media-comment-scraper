"""
Enhanced multi-step progress tracker for One Search pipeline.
"""

import streamlit as st


PIPELINE_STEPS = [
    {"label": "Searching for relevant content", "icon": "1"},
    {"label": "Collecting URLs across platforms", "icon": "2"},
    {"label": "Scraping comments", "icon": "3"},
    {"label": "Running analysis", "icon": "4"},
    {"label": "Generating insights", "icon": "5"},
]


class OneSearchProgress:
    """Multi-step progress tracker for the One Search pipeline."""

    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.current_step = 0
        self.total_steps = len(PIPELINE_STEPS)
        self.sub_message = ""
        self.comment_count = 0
        self.done = False
        self._render()

    def set_step(self, step: int, message: str = ""):
        """Advance to a specific step."""
        self.current_step = min(step, self.total_steps - 1)
        self.sub_message = message
        self._render()

    def on_message(self, msg: str):
        """Handle a progress message from the pipeline."""
        msg = str(msg).strip()
        if not msg:
            return

        self.sub_message = msg

        # Auto-detect step from message content
        msg_lower = msg.lower()
        if "search" in msg_lower and "query" in msg_lower:
            self.current_step = 0
        elif "found" in msg_lower and "url" in msg_lower:
            self.current_step = 1
        elif "scrap" in msg_lower:
            self.current_step = 2
        elif "analyz" in msg_lower or "analysis" in msg_lower:
            self.current_step = 3
        elif "insight" in msg_lower or "ai" in msg_lower:
            self.current_step = 4

        # Extract comment counts
        import re
        count_match = re.search(r'(\d+)\s+(?:total\s+)?comments?', msg, re.IGNORECASE)
        if count_match:
            self.comment_count = max(self.comment_count, int(count_match.group(1)))

        self._render()

    def complete(self, total_comments: int):
        """Mark the pipeline as complete."""
        self.done = True
        self.comment_count = total_comments
        self.current_step = self.total_steps
        self._render()

    def _render(self):
        """Render the multi-step progress panel."""
        steps_html = ""
        for i, step in enumerate(PIPELINE_STEPS):
            if self.done or i < self.current_step:
                status = "done"
                dot_class = "osp-dot osp-dot-done"
            elif i == self.current_step and not self.done:
                status = "active"
                dot_class = "osp-dot osp-dot-active"
            else:
                status = "pending"
                dot_class = "osp-dot osp-dot-pending"

            steps_html += (
                f'<div class="osp-step osp-step-{status}">'
                f'<span class="{dot_class}">{step["icon"]}</span>'
                f'<span class="osp-step-label">{step["label"]}</span>'
                f'</div>'
            )

        if self.done:
            message = f"Research complete! Found {self.comment_count} comments"
            message_class = "osp-msg-done"
        else:
            message = self.sub_message or PIPELINE_STEPS[self.current_step]["label"] + "..."
            message_class = "osp-msg-active"

        html = (
            '<div class="osp-panel">'
            "<style>"
            ".osp-panel{background:rgba(255,255,255,0.035);"
            "border:1px solid rgba(255,255,255,0.06);"
            "border-radius:14px;padding:1.25rem;"
            "backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);"
            "font-family:'Inter','Helvetica Neue',sans-serif;"
            "margin:1rem 0}"
            ".osp-steps{display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap}"
            ".osp-step{display:flex;align-items:center;gap:0.35rem;padding:4px 10px;"
            "border-radius:6px;font-size:0.78rem}"
            ".osp-step-done{color:#34D399}"
            ".osp-step-active{color:#3B82F6;background:rgba(59,130,246,0.08)}"
            ".osp-step-pending{color:#64748B}"
            ".osp-dot{width:18px;height:18px;border-radius:50%;display:inline-flex;"
            "align-items:center;justify-content:center;font-size:0.65rem;font-weight:600}"
            ".osp-dot-done{background:rgba(52,211,153,0.15);color:#34D399}"
            ".osp-dot-active{background:rgba(59,130,246,0.15);color:#3B82F6;"
            "animation:osp-pulse 1.5s ease infinite}"
            ".osp-dot-pending{background:rgba(100,116,139,0.1);color:#64748B}"
            ".osp-msg{font-size:0.85rem;color:#E2E8F0;margin-top:0.5rem}"
            ".osp-msg-done{color:#34D399}"
            f".osp-counter{{font-size:1.4rem;font-weight:700;color:#E2E8F0;"
            f"font-family:'JetBrains Mono',monospace;float:right;margin-top:-1.5rem}}"
            "@keyframes osp-pulse{0%,100%{opacity:1}50%{opacity:0.4}}"
            "</style>"
            f'<div class="osp-steps">{steps_html}</div>'
            f'<div class="osp-counter">{self.comment_count}</div>'
            f'<div class="osp-msg {message_class}">{message}</div>'
            "</div>"
        )

        self.placeholder.markdown(html, unsafe_allow_html=True)
