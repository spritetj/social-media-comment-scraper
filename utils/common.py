"""
Shared utilities for Social Media Comment Scraper web app.
"""

import asyncio
import csv
import io
import json
import re


class AdaptiveDelay:
    """Adaptive rate-limiting: speeds up on success, backs off on errors/429s."""

    def __init__(self, min_delay=0.3, max_delay=10.0, initial=2.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.delay = initial

    async def wait(self):
        await asyncio.sleep(self.delay)

    def on_success(self):
        self.delay = max(self.min_delay, self.delay * 0.85)

    def on_error(self):
        self.delay = min(self.max_delay, self.delay * 2.0)

    def on_rate_limit(self):
        self.delay = min(self.max_delay, self.delay * 3.0)


def fmt_num(n) -> str:
    """Format a number with K/M suffixes for display."""
    if not isinstance(n, (int, float)):
        return str(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def _parse_count_string(text: str) -> int:
    """Parse count strings like '1.2K', '3M', '42' to integers."""
    if not text:
        return 0
    text = text.strip().upper().replace(",", "")
    text = re.sub(r'[^0-9KMB.]', '', text)
    try:
        if text.endswith("B"):
            return int(float(text[:-1]) * 1_000_000_000)
        if text.endswith("M"):
            return int(float(text[:-1]) * 1_000_000)
        if text.endswith("K"):
            return int(float(text[:-1]) * 1_000)
        return int(float(text))
    except (ValueError, IndexError):
        return 0


def load_cookies_generic(file_content: str, domain_filter: str) -> dict:
    """Load cookies from uploaded file content (Netscape .txt or JSON format).
    Returns a dict of {name: value} for the given domain."""
    cookies = {}
    content = file_content.strip()

    if content.startswith("#") or "\t" in content.split("\n")[0]:
        # Netscape cookies.txt format
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, _, path_val, _, _, name, value = parts[:7]
                if name and value and domain_filter in domain:
                    cookies[name] = value
    else:
        # JSON format
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    name = item.get("name", "")
                    value = item.get("value", "")
                    domain = item.get("domain", "")
                    if name and value and domain_filter in domain:
                        cookies[name] = str(value)
            elif isinstance(data, dict):
                cookies = {k: str(v) for k, v in data.items() if v}
        except json.JSONDecodeError:
            pass

    return cookies


def load_cookies_as_list(file_content: str, domain_filter: str) -> list[dict]:
    """Load cookies from uploaded file content as a list of cookie dicts
    (for Playwright context.add_cookies). Returns list of {name, value, domain, path}."""
    cookies = []
    content = file_content.strip()

    if content.startswith("#") or "\t" in content.split("\n")[0]:
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, _, path_val, _, _, name, value = parts[:7]
                if name and value and domain_filter in domain:
                    cookies.append({
                        "name": name, "value": value,
                        "domain": domain, "path": path_val,
                    })
    else:
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    name = item.get("name", "")
                    value = item.get("value", "")
                    domain = item.get("domain", f".{domain_filter}")
                    if name and value and domain_filter in domain:
                        cookies.append({
                            "name": name, "value": str(value),
                            "domain": domain, "path": item.get("path", "/"),
                        })
            elif isinstance(data, dict):
                for name, value in data.items():
                    if value:
                        cookies.append({
                            "name": name, "value": str(value),
                            "domain": f".{domain_filter}", "path": "/",
                        })
        except json.JSONDecodeError:
            pass

    return cookies


def export_csv_bytes(comments: list[dict], clean_mode: bool = False, platform: str = "") -> bytes:
    """Export comments list to CSV bytes (for Streamlit download button).
    If clean_mode=True, normalizes to clean schema first."""
    if not comments:
        return b""
    if clean_mode and platform:
        from utils.schema import to_clean
        comments = to_clean(comments, platform)
    output = io.StringIO()
    fieldnames = list(comments[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for c in comments:
        row = {}
        for k, v in c.items():
            row[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def export_json_bytes(comments: list[dict], clean_mode: bool = False, platform: str = "") -> bytes:
    """Export comments list to JSON bytes (for Streamlit download button).
    If clean_mode=True, normalizes to clean schema first."""
    if not comments:
        return b"[]"
    if clean_mode and platform:
        from utils.schema import to_clean
        comments = to_clean(comments, platform)
    return json.dumps(comments, indent=2, ensure_ascii=False, default=str).encode("utf-8")
