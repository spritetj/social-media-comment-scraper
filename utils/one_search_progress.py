"""
Enhanced multi-step progress tracker for One Search pipeline.
"""

import html as html_module

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
        self.research_question = ""
        self.hypotheses: list[str] = []
        self.detail_log: list[str] = []
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

        # Capture research context from LLM strategist messages
        if msg.startswith("Research: "):
            self.research_question = msg[len("Research: "):]
        elif msg.startswith("Hypotheses: "):
            self.hypotheses = [h.strip() for h in msg[len("Hypotheses: "):].split(";") if h.strip()]

        self.sub_message = msg

        # Accumulate detail log (last 8 entries)
        self.detail_log.append(msg)
        if len(self.detail_log) > 8:
            self.detail_log = self.detail_log[-8:]

        # Auto-detect step from message content
        msg_lower = msg.lower()
        if msg.startswith("Query:"):
            self.current_step = 0
        elif "search" in msg_lower and "query" in msg_lower:
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

        # Build research context section (shown when LLM provides hypotheses)
        research_html = ""
        if self.research_question or self.hypotheses:
            research_html = '<div class="osp-research">'
            if self.research_question:
                research_html += (
                    f'<div class="osp-rq">{self.research_question}</div>'
                )
            if self.hypotheses:
                hyp_items = "".join(
                    f'<span class="osp-hyp">{h}</span>' for h in self.hypotheses
                )
                research_html += f'<div class="osp-hyps">{hyp_items}</div>'
            research_html += "</div>"

        # Build detail log section (only shown during execution)
        detail_log_html = ""
        if not self.done and self.detail_log:
            log_items = "".join(
                f'<div class="osp-log-item">{html_module.escape(entry)}</div>'
                for entry in self.detail_log[-6:]
            )
            detail_log_html = f'<div class="osp-log">{log_items}</div>'

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
            ".osp-research{margin:0.75rem 0;padding:0.6rem 0.8rem;"
            "background:rgba(99,102,241,0.06);border-left:2px solid rgba(99,102,241,0.3);"
            "border-radius:0 6px 6px 0}"
            ".osp-rq{font-size:0.82rem;color:#A5B4FC;margin-bottom:0.4rem;"
            "font-weight:500}"
            ".osp-hyps{display:flex;flex-wrap:wrap;gap:0.3rem}"
            ".osp-hyp{font-size:0.72rem;color:#94A3B8;padding:2px 8px;"
            "background:rgba(255,255,255,0.04);border-radius:4px}"
            f".osp-counter{{font-size:1.4rem;font-weight:700;color:#E2E8F0;"
            f"font-family:'JetBrains Mono',monospace;float:right;margin-top:-1.5rem}}"
            "@keyframes osp-pulse{0%,100%{opacity:1}50%{opacity:0.4}}"
            ".osp-log{margin-top:0.75rem;padding:0.5rem;background:rgba(0,0,0,0.15);"
            "border-radius:6px;max-height:140px;overflow-y:auto;font-family:monospace}"
            ".osp-log-item{font-size:0.7rem;color:#94A3B8;padding:2px 0;"
            "border-bottom:1px solid rgba(255,255,255,0.03);white-space:nowrap;"
            "overflow:hidden;text-overflow:ellipsis}"
            "</style>"
            f'<div class="osp-steps">{steps_html}</div>'
            f'{research_html}'
            f'<div class="osp-counter">{self.comment_count}</div>'
            f'<div class="osp-msg {message_class}">{message}</div>'
            f'{detail_log_html}'
            "</div>"
        )

        self.placeholder.markdown(html, unsafe_allow_html=True)
