"""
Facebook Comment Scraper — Streamlit Page
"""

import streamlit as st
import nest_asyncio
import asyncio
import time
from pathlib import Path

nest_asyncio.apply()

st.set_page_config(
    page_title="Facebook — Comment Scraper",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load custom CSS
css_path = Path(__file__).parent.parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Navigation — compact centered
_, n1, n2, n3, n4, n5, n6, _ = st.columns([3, 1, 1, 1, 1, 1, 0.8, 3])
with n1:
    st.page_link("Home.py", label="Home")
with n2:
    st.page_link("pages/1_🎬_YouTube.py", label="YouTube")
with n3:
    st.page_link("pages/2_🎵_TikTok.py", label="TikTok")
with n4:
    st.page_link("pages/3_📘_Facebook.py", label="Facebook")
with n5:
    st.page_link("pages/4_📷_Instagram.py", label="Instagram")
with n6:
    qr_path = Path(__file__).parent.parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)

# Page header
st.markdown('<div class="page-header"><h1>Facebook</h1></div>', unsafe_allow_html=True)
st.markdown('<p class="page-desc">Scrape comments from Facebook posts, reels, and videos.</p>', unsafe_allow_html=True)

# URL input
url_input = st.text_area(
    "Enter Facebook post URL(s)",
    placeholder="https://www.facebook.com/username/posts/123456789\nhttps://www.facebook.com/reel/123456789",
    height=100,
    label_visibility="collapsed",
)

# Authentication expander — cookies required
with st.expander("Authentication (required)", expanded=True):
    st.markdown(
        "Facebook requires cookies for authentication. "
        "[How to export cookies](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)",
    )
    cookie_file = st.file_uploader(
        "Upload cookies.txt or cookies.json",
        type=["txt", "json"],
        help="Export cookies from your browser while logged into Facebook",
    )

# Start button
scrape_btn = st.button("Start Scraping", type="primary", use_container_width=True)

# Results area
if scrape_btn and url_input.strip():
    urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

    if not urls:
        st.warning("Please enter at least one Facebook URL.")
        st.stop()

    if not cookie_file:
        st.error("Please upload your Facebook cookies file above.")
        st.stop()

    # Import scraper
    try:
        from scrapers.facebook import scrape_comments_fast
        from utils.common import load_cookies_as_list, export_csv_bytes, export_json_bytes, fmt_num
        from utils.progress_ui import ProgressTracker
    except ImportError as e:
        st.error(f"Import error: {e}. Make sure you're running from the project directory.")
        st.stop()

    # Load cookies
    cookie_content = cookie_file.read().decode("utf-8")
    cookies = load_cookies_as_list(cookie_content, "facebook.com")
    if not cookies:
        st.error("Could not parse cookies from the uploaded file. Make sure it's a valid cookies.txt or JSON file.")
        st.stop()

    # Progress display
    progress_placeholder = st.empty()
    tracker = ProgressTracker(total_videos=len(urls), placeholder=progress_placeholder)
    all_comments = []

    # Run scraper
    start_time = time.time()

    loop = asyncio.new_event_loop()
    for i, url in enumerate(urls):
        tracker.on_message(f"--- Post {i+1}/{len(urls)} ---")
        try:
            comments = loop.run_until_complete(
                scrape_comments_fast(url, cookies=cookies, progress_callback=tracker.on_message)
            )
            if comments:
                all_comments.extend(comments)
                tracker.on_message(f"Got {len(comments)} comments!")
            else:
                tracker.on_message("No comments found for this post")
        except Exception as e:
            tracker.on_message(f"Something went wrong. Please try again.")
    loop.close()

    elapsed = time.time() - start_time
    tracker.complete(len(all_comments), elapsed)

    # Results
    if all_comments:
        st.markdown("")

        # Summary metrics
        replies = [c for c in all_comments if c.get("threadingDepth", 0) > 0]
        total_likes = sum(int(c.get("likesCount", 0) or 0) for c in all_comments)

        m1, m2, m3 = st.columns(3)
        m1.metric("Comments", fmt_num(len(all_comments)))
        m2.metric("Replies", fmt_num(len(replies)))
        m3.metric("Total Likes", fmt_num(total_likes))

        # Data table
        import pandas as pd
        df = pd.DataFrame(all_comments)
        display_cols = ["profileName", "text", "likesCount", "commentsCount", "date", "threadingDepth"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=400)

        # Download buttons
        st.markdown("")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Export CSV",
                data=export_csv_bytes(all_comments),
                file_name="facebook_comments.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Export JSON",
                data=export_json_bytes(all_comments),
                file_name="facebook_comments.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("No comments were found. The post may have no comments or require different cookies.")

elif scrape_btn:
    st.warning("Please enter at least one Facebook URL above.")
