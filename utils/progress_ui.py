"""
Progress UI — Apple-inspired progress panel for scraping operations.
Renders structured HTML progress display via st.empty() placeholder.
"""

import re


class ProgressTracker:
    """
    Parses raw scraper progress messages into structured state
    and renders an Apple-inspired progress panel via Streamlit.
    """

    def __init__(self, total_videos: int, placeholder):
        self.total = total_videos
        self.placeholder = placeholder
        self.current_index = 0  # 0-based
        self.total_comments = 0
        self.steps = []  # list of dicts: {title, count, status, action}
        self.current_action = ""
        self.done = False

        # Initialize pending steps
        for i in range(total_videos):
            self.steps.append({
                "title": f"Video {i + 1}",
                "count": 0,
                "status": "pending",  # pending | active | completed | error
                "action": "",
            })

        self._render()

    def on_message(self, msg: str):
        """Parse a progress callback message and update state."""
        msg = str(msg).strip()
        if not msg:
            return

        # Detect video boundary: "--- Video 2/3 ---" or "--- Post 1/2 ---"
        boundary = re.match(r"^---\s*(?:Video|Post)\s*(\d+)/(\d+)\s*---$", msg)
        if boundary:
            idx = int(boundary.group(1)) - 1
            # Mark previous as completed if it was active
            if self.current_index < len(self.steps) and self.steps[self.current_index]["status"] == "active":
                self.steps[self.current_index]["status"] = "completed"
            self.current_index = idx
            if idx < len(self.steps):
                self.steps[idx]["status"] = "active"
                self.steps[idx]["action"] = "Starting..."
            self._render()
            return

        # Detect title: "Title: ..." or "Caption: ..."
        title_match = re.match(r"^(?:Title|Caption):\s*(.+)$", msg)
        if title_match and self.current_index < len(self.steps):
            title = title_match.group(1).strip()
            if len(title) > 50:
                title = title[:47] + "..."
            self.steps[self.current_index]["title"] = title
            self._render()
            return

        # Detect count update: "Found N comments" or "Fetched N comments"
        count_match = re.match(r"^(?:Found|Fetched)\s+(\d+)\s+comments?", msg, re.IGNORECASE)
        if count_match and self.current_index < len(self.steps):
            self.steps[self.current_index]["count"] = int(count_match.group(1))
            self._render()
            return

        # Detect completion: "Got N comments!"
        got_match = re.match(r"^Got\s+(\d+)\s+comments?", msg, re.IGNORECASE)
        if got_match and self.current_index < len(self.steps):
            count = int(got_match.group(1))
            self.steps[self.current_index]["count"] = count
            self.steps[self.current_index]["status"] = "completed"
            self.steps[self.current_index]["action"] = ""
            self.total_comments = sum(s["count"] for s in self.steps)
            self._render()
            return

        # Detect no comments
        if re.match(r"^No comments found", msg, re.IGNORECASE) and self.current_index < len(self.steps):
            self.steps[self.current_index]["status"] = "completed"
            self.steps[self.current_index]["count"] = 0
            self.steps[self.current_index]["action"] = ""
            self._render()
            return

        # Detect error
        if "went wrong" in msg.lower() or "error" in msg.lower():
            if self.current_index < len(self.steps):
                self.steps[self.current_index]["status"] = "error"
                self.steps[self.current_index]["action"] = "Failed"
            self._render()
            return

        # General action message
        if self.current_index < len(self.steps) and self.steps[self.current_index]["status"] == "active":
            action = msg
            if len(action) > 60:
                action = action[:57] + "..."
            self.steps[self.current_index]["action"] = action
            self._render()

    def complete(self, total: int, elapsed: float):
        """Mark the entire operation as complete."""
        self.done = True
        self.total_comments = total
        # Mark any remaining active steps as completed
        for step in self.steps:
            if step["status"] == "active":
                step["status"] = "completed"
        self.elapsed = elapsed
        self._render()

    def _render(self):
        """Render the progress panel HTML."""
        self.total_comments = sum(s["count"] for s in self.steps)
        html = self._build_html()
        self.placeholder.markdown(html, unsafe_allow_html=True)

    def _build_html(self) -> str:
        completed = sum(1 for s in self.steps if s["status"] == "completed")
        progress_pct = (completed / self.total * 100) if self.total > 0 else 0

        if self.done:
            status_dot = '<span class="prg-dot prg-dot-done"></span>'
            status_label = f"Complete — {self.total_comments} comments"
            if hasattr(self, "elapsed"):
                status_label += f" in {self.elapsed:.1f}s"
        else:
            active_idx = next((i for i, s in enumerate(self.steps) if s["status"] == "active"), None)
            if active_idx is not None:
                status_dot = '<span class="prg-dot prg-dot-active"></span>'
                status_label = f"Scraping video {active_idx + 1} of {self.total}..."
            else:
                status_dot = '<span class="prg-dot"></span>'
                status_label = "Preparing..."

        # Build step items
        step_items = ""
        for i, step in enumerate(self.steps):
            if step["status"] == "completed":
                icon = '<span class="prg-step-icon prg-check">&#10003;</span>'
                title_class = "prg-step-title"
                count_html = f'<span class="prg-step-count">{step["count"]} comments</span>' if step["count"] else '<span class="prg-step-count">0 comments</span>'
                action_html = ""
            elif step["status"] == "active":
                icon = '<span class="prg-step-icon prg-spinner"></span>'
                title_class = "prg-step-title prg-step-active"
                count_html = f'<span class="prg-step-count">{step["count"]} comments</span>' if step["count"] else ""
                action_html = f'<div class="prg-step-action">{step["action"]}</div>' if step["action"] else ""
            elif step["status"] == "error":
                icon = f'<span class="prg-step-icon prg-error">!</span>'
                title_class = "prg-step-title prg-step-err"
                count_html = '<span class="prg-step-count prg-err-text">Failed</span>'
                action_html = ""
            else:
                icon = f'<span class="prg-step-icon prg-pending">{i + 1}</span>'
                title_class = "prg-step-title prg-step-pending"
                count_html = ""
                action_html = ""

            step_items += f"""
            <div class="prg-step">
                <div class="prg-step-row">
                    {icon}
                    <span class="{title_class}">{step["title"]}</span>
                    {count_html}
                </div>
                {action_html}
            </div>"""

        bar_class = "prg-bar-fill prg-bar-done" if self.done else "prg-bar-fill prg-bar-active"

        return f"""
<div class="prg-panel">
    <style>
        .prg-panel {{
            background: #1C1C1E;
            border: 1px solid rgba(240,238,233,0.08);
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
            margin: 1rem 0;
        }}
        .prg-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.75rem;
        }}
        .prg-header-left {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .prg-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #48484A;
            display: inline-block;
        }}
        .prg-dot-active {{
            background: #30D158;
            animation: prg-pulse 1.5s ease infinite;
        }}
        .prg-dot-done {{
            background: #30D158;
        }}
        .prg-label {{
            font-size: 0.875rem;
            color: #F0EEE9;
            font-weight: 500;
        }}
        .prg-counter {{
            font-size: 1.75rem;
            font-weight: 700;
            color: #F0EEE9;
            letter-spacing: -0.02em;
            line-height: 1;
        }}
        .prg-bar {{
            height: 3px;
            background: #2C2C2E;
            border-radius: 2px;
            margin-bottom: 1rem;
            overflow: hidden;
        }}
        .prg-bar-fill {{
            height: 100%;
            border-radius: 2px;
            transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .prg-bar-active {{
            background: linear-gradient(90deg, #F0EEE9, rgba(240,238,233,0.6));
            animation: prg-shimmer 2s linear infinite;
            background-size: 200% 100%;
        }}
        .prg-bar-done {{
            background: #30D158;
        }}
        .prg-step {{
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(240,238,233,0.04);
        }}
        .prg-step:last-child {{
            border-bottom: none;
        }}
        .prg-step-row {{
            display: flex;
            align-items: center;
            gap: 0.625rem;
        }}
        .prg-step-icon {{
            width: 22px;
            height: 22px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
            font-weight: 600;
            flex-shrink: 0;
        }}
        .prg-check {{
            background: rgba(48,209,88,0.15);
            color: #30D158;
            font-size: 0.75rem;
        }}
        .prg-spinner {{
            border: 2px solid #2C2C2E;
            border-top: 2px solid #F0EEE9;
            animation: prg-spin 0.8s linear infinite;
            background: transparent;
        }}
        .prg-pending {{
            background: #2C2C2E;
            color: #48484A;
        }}
        .prg-error {{
            background: rgba(255,69,58,0.15);
            color: #FF453A;
        }}
        .prg-step-title {{
            font-size: 0.875rem;
            color: #F0EEE9;
            font-weight: 500;
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .prg-step-active {{
            color: #F0EEE9;
        }}
        .prg-step-pending {{
            color: #48484A;
        }}
        .prg-step-err {{
            color: #FF453A;
        }}
        .prg-step-count {{
            font-size: 0.8rem;
            color: #8E8E93;
            white-space: nowrap;
            flex-shrink: 0;
        }}
        .prg-err-text {{
            color: #FF453A;
        }}
        .prg-step-action {{
            font-size: 0.8rem;
            color: #8E8E93;
            margin-left: 2.125rem;
            margin-top: 0.2rem;
        }}
        @keyframes prg-pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}
        @keyframes prg-spin {{
            to {{ transform: rotate(360deg); }}
        }}
        @keyframes prg-shimmer {{
            0% {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}
    </style>
    <div class="prg-header">
        <div class="prg-header-left">
            {status_dot}
            <span class="prg-label">{status_label}</span>
        </div>
        <span class="prg-counter">{self.total_comments}</span>
    </div>
    <div class="prg-bar">
        <div class="{bar_class}" style="width: {progress_pct}%"></div>
    </div>
    {step_items}
</div>"""
