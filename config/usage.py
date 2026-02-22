"""
Session-based usage tracking for MVP.
Tracks feature usage within a session to enforce soft limits.
"""

import streamlit as st
from datetime import datetime


def _get_usage() -> dict:
    """Get usage data from session state."""
    if "usage" not in st.session_state:
        st.session_state["usage"] = {
            "urls_scraped": 0,
            "one_searches": 0,
            "ai_analyses": 0,
            "session_start": datetime.now().isoformat(),
        }
    return st.session_state["usage"]


def track_url_scrape(count: int = 1):
    """Track a URL scrape."""
    usage = _get_usage()
    usage["urls_scraped"] += count


def track_one_search():
    """Track a One Search query."""
    usage = _get_usage()
    usage["one_searches"] += 1


def track_ai_analysis():
    """Track an AI analysis run."""
    usage = _get_usage()
    usage["ai_analyses"] += 1


def get_urls_scraped() -> int:
    """Get number of URLs scraped in this session."""
    return _get_usage()["urls_scraped"]


def get_one_searches() -> int:
    """Get number of One Search queries in this session."""
    return _get_usage()["one_searches"]


def get_ai_analyses() -> int:
    """Get number of AI analyses in this session."""
    return _get_usage()["ai_analyses"]


def get_usage_summary() -> dict:
    """Get a summary of current session usage."""
    usage = _get_usage()
    return {
        "urls_scraped": usage["urls_scraped"],
        "one_searches": usage["one_searches"],
        "ai_analyses": usage["ai_analyses"],
        "session_start": usage["session_start"],
    }
