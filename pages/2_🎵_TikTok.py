"""
TikTok Comment Scraper — Streamlit Page
"""

import streamlit as st
import time
from pathlib import Path

from utils.async_runner import run_async

st.set_page_config(
    page_title="TikTok — Comment Scraper",
    page_icon="🎵",
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
st.markdown('<div class="page-header"><h1>TikTok</h1></div>', unsafe_allow_html=True)
st.markdown('<p class="page-desc">Extract comments and replies from TikTok videos.</p>', unsafe_allow_html=True)

# URL input
url_input = st.text_area(
    "Enter TikTok video URL(s)",
    placeholder="https://www.tiktok.com/@username/video/1234567890\nhttps://vm.tiktok.com/abcdef/",
    height=100,
    label_visibility="collapsed",
)

# Settings expander
with st.expander("Settings"):
    s1, s2 = st.columns(2)
    with s1:
        max_comments = st.slider(
            "Max comments per video",
            min_value=0, max_value=5000, value=0, step=100,
            help="0 = fetch all comments",
        )
    with s2:
        max_replies = st.slider(
            "Max replies per comment",
            min_value=-1, max_value=100, value=5, step=1,
            help="-1 = skip replies, 0 = all replies",
        )
    output_mode = st.radio("Output mode", ["Clean (analysis-ready)", "Raw (all fields)"], index=0, horizontal=True)

# Start button
scrape_btn = st.button("Start Scraping", type="primary", use_container_width=True)

# Results area
if scrape_btn and url_input.strip():
    urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

    if not urls:
        st.warning("Please enter at least one TikTok URL.")
        st.stop()

    # Import scraper
    try:
        from scrapers.tiktok import TikTokCommentScraper
        from utils.common import export_csv_bytes, export_json_bytes, fmt_num
        from utils.progress_ui import ProgressTracker
        from utils.schema import to_clean
    except ImportError as e:
        st.error(f"Import error: {e}. Make sure you're running from the project directory.")
        st.stop()

    # Progress display
    progress_placeholder = st.empty()
    tracker = ProgressTracker(total_videos=len(urls), placeholder=progress_placeholder)
    all_comments = []

    # Create scraper
    scraper = TikTokCommentScraper(
        headless=True,
        max_comments=max_comments,
        max_replies=max_replies,
        progress_callback=tracker.on_message,
    )

    # Run scraper
    start_time = time.time()

    for i, url in enumerate(urls):
        tracker.on_message(f"--- Video {i+1}/{len(urls)} ---")
        try:
            comments = run_async(scraper.scrape_video_comments(url))
            if comments:
                all_comments.extend(comments)
                tracker.on_message(f"Got {len(comments)} comments!")
            else:
                tracker.on_message("No comments found for this video")
        except Exception as e:
            tracker.on_message(f"Something went wrong. Please try again.")

    elapsed = time.time() - start_time
    tracker.complete(len(all_comments), elapsed)

    # Store in session state for analysis
    clean_mode = output_mode.startswith("Clean")
    if all_comments:
        clean_comments = to_clean(all_comments, "tiktok")
        st.session_state["last_scrape"] = {
            "comments": clean_comments,
            "raw_comments": all_comments,
            "platform": "tiktok",
            "count": len(all_comments),
        }

    # Results
    if all_comments:
        st.markdown("")

        # Summary metrics
        replies = [c for c in all_comments if c.get("is_reply")]
        total_likes = sum(c.get("like_count", 0) for c in all_comments)

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
            display_cols = ["username", "text", "like_count", "reply_count", "created_at", "is_reply"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=400)

        # Download buttons
        st.markdown("")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Export CSV",
                data=export_csv_bytes(all_comments, clean_mode=clean_mode, platform="tiktok"),
                file_name="tiktok_comments.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Export JSON",
                data=export_json_bytes(all_comments, clean_mode=clean_mode, platform="tiktok"),
                file_name="tiktok_comments.json",
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
        st.info("No comments were found. The video may have no comments or comments may be disabled.")

elif scrape_btn:
    st.warning("Please enter at least one TikTok URL above.")
