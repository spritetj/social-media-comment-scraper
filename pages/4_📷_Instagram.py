"""
Instagram Comment Scraper — Streamlit Page
"""

import streamlit as st
import time
from pathlib import Path

from utils.async_runner import run_async

st.set_page_config(
    page_title="Instagram — Comment Scraper",
    page_icon="📷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load custom CSS
css_path = Path(__file__).parent.parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Navigation
from utils.nav import render_nav
render_nav()

# Page header
st.markdown('<div class="page-header"><h1>Instagram</h1></div>', unsafe_allow_html=True)
st.markdown('<p class="page-desc">Scrape comments from Instagram posts and reels.</p>', unsafe_allow_html=True)

# URL input
url_input = st.text_area(
    "Enter Instagram post URL(s)",
    placeholder="https://www.instagram.com/p/ABC123/\nhttps://www.instagram.com/reel/XYZ789/",
    height=100,
    label_visibility="collapsed",
)

# Authentication expander
with st.expander("Authentication (optional)"):
    st.markdown(
        "Cookies are optional but recommended for more results. "
        "[How to export cookies](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)",
    )
    cookie_file = st.file_uploader(
        "Upload cookies.txt or cookies.json",
        type=["txt", "json"],
        help="Export cookies from your browser while logged into Instagram",
    )

# Settings
with st.expander("Settings"):
    output_mode = st.radio("Output mode", ["Clean (analysis-ready)", "Raw (all fields)"], index=0, horizontal=True)

# Start button
scrape_btn = st.button("Start Scraping", type="primary", use_container_width=True)

# Results area
if scrape_btn and url_input.strip():
    urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

    if not urls:
        st.warning("Please enter at least one Instagram URL.")
        st.stop()

    # Import scraper
    try:
        from scrapers.instagram import scrape_post_urls
        from utils.common import load_cookies_as_list, export_csv_bytes, export_json_bytes, fmt_num
        from utils.progress_ui import ProgressTracker
        from utils.schema import to_clean
    except ImportError as e:
        st.error(f"Import error: {e}. Make sure you're running from the project directory.")
        st.stop()

    # Load cookies if uploaded
    cookies = None
    if cookie_file:
        cookie_content = cookie_file.read().decode("utf-8")
        cookies = load_cookies_as_list(cookie_content, "instagram.com")

    # Progress display
    progress_placeholder = st.empty()
    tracker = ProgressTracker(total_videos=len(urls), placeholder=progress_placeholder)

    # Run scraper
    start_time = time.time()

    try:
        all_comments = run_async(
            scrape_post_urls(urls, cookies=cookies, progress_callback=tracker.on_message)
        )
    except Exception as e:
        all_comments = []
        tracker.on_message(f"Something went wrong. Please try again.")

    elapsed = time.time() - start_time
    tracker.complete(len(all_comments), elapsed)

    # Store in session state for analysis
    clean_mode = output_mode.startswith("Clean")
    if all_comments:
        clean_comments = to_clean(all_comments, "instagram")
        st.session_state["last_scrape"] = {
            "comments": clean_comments,
            "raw_comments": all_comments,
            "platform": "instagram",
            "count": len(all_comments),
        }

    # Results
    if all_comments:
        st.markdown("")

        # Summary metrics
        replies = [c for c in all_comments if c.get("threadingDepth", 0) > 0]
        total_likes = sum(c.get("likesCount", 0) for c in all_comments)

        m1, m2, m3 = st.columns(3)
        m1.metric("Comments", fmt_num(len(all_comments)))
        m2.metric("Replies", fmt_num(len(replies)))
        m3.metric("Total Likes", fmt_num(total_likes))

        # Data table
        import pandas as pd
        if clean_mode:
            df = pd.DataFrame(clean_comments)
            display_cols = ["username", "text", "likes", "replies", "date", "is_reply"]
        else:
            df = pd.DataFrame(all_comments)
            display_cols = ["ownerUsername", "text", "likesCount", "repliesCount", "date", "threadingDepth"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=400)

        # Download buttons
        st.markdown("")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Export CSV",
                data=export_csv_bytes(all_comments, clean_mode=clean_mode, platform="instagram"),
                file_name="instagram_comments.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Export JSON",
                data=export_json_bytes(all_comments, clean_mode=clean_mode, platform="instagram"),
                file_name="instagram_comments.json",
                mime="application/json",
                use_container_width=True,
            )

        # Analysis dashboard
        if len(all_comments) >= 10:
            try:
                from analysis.pipeline import run_full_analysis
                from utils.analysis_ui import render_analysis_dashboard
                with st.spinner("Analyzing..."):
                    analysis = run_full_analysis(clean_comments)
                render_analysis_dashboard(analysis)
            except ImportError:
                pass
    else:
        st.info("No comments were found. The post may have no comments or require login.")

elif scrape_btn:
    st.warning("Please enter at least one Instagram URL above.")
