"""
Facebook Comment Scraper — Streamlit Page
"""

import streamlit as st
import nest_asyncio
import asyncio
import time
from pathlib import Path

nest_asyncio.apply()

st.set_page_config(page_title="Facebook Scraper", page_icon="📘", layout="wide")

# Load custom CSS
css_path = Path(__file__).parent.parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

st.markdown("## 📘 Facebook Comment Scraper")
st.markdown("Scrape comments from Facebook posts, reels, and videos.")
st.markdown("---")

# Cookie requirement notice
st.info(
    "**Cookies Required:** Facebook requires authentication to access comments. "
    "Upload your Facebook cookies file below. "
    "[How to export cookies](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)"
)

# Sidebar settings
with st.sidebar:
    st.markdown("### Cookies")
    cookie_file = st.file_uploader(
        "Upload cookies.txt or cookies.json",
        type=["txt", "json"],
        help="Export cookies from your browser while logged into Facebook",
    )

    st.markdown("---")
    qr_path = Path(__file__).parent.parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("☕ Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

# Main input
url_input = st.text_area(
    "Enter Facebook post URL(s)",
    placeholder="https://www.facebook.com/username/posts/123456789\nhttps://www.facebook.com/reel/123456789",
    height=100,
    help="One URL per line. Supports posts, reels, videos, and photos.",
)

col_btn, col_info = st.columns([1, 3])
with col_btn:
    scrape_btn = st.button("🚀 Start Scraping", type="primary", use_container_width=True)
with col_info:
    st.caption("Requires cookies for authentication.")

# Results area
if scrape_btn and url_input.strip():
    urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

    if not urls:
        st.warning("Please enter at least one Facebook URL.")
        st.stop()

    if not cookie_file:
        st.error("Please upload your Facebook cookies file in the sidebar.")
        st.stop()

    # Import scraper
    try:
        from scrapers.facebook import scrape_comments_fast
        from utils.common import load_cookies_as_list, export_csv_bytes, export_json_bytes, fmt_num
    except ImportError as e:
        st.error(f"Import error: {e}. Make sure you're running from the project directory.")
        st.stop()

    # Load cookies
    cookie_content = cookie_file.read().decode("utf-8")
    cookies = load_cookies_as_list(cookie_content, "facebook.com")
    if not cookies:
        st.error("Could not parse cookies from the uploaded file. Make sure it's a valid cookies.txt or JSON file.")
        st.stop()

    st.sidebar.success(f"Loaded {len(cookies)} cookies")

    # Progress display
    progress_container = st.status(f"Scraping {len(urls)} post(s)...", expanded=True)
    all_comments = []

    def on_progress(msg):
        progress_container.write(msg)

    # Run scraper
    start_time = time.time()

    loop = asyncio.new_event_loop()
    for i, url in enumerate(urls):
        on_progress(f"--- Post {i+1}/{len(urls)} ---")
        try:
            comments = loop.run_until_complete(
                scrape_comments_fast(url, cookies=cookies, progress_callback=on_progress)
            )
            if comments:
                all_comments.extend(comments)
                on_progress(f"Got {len(comments)} comments!")
            else:
                on_progress("No comments found for this post")
        except Exception as e:
            on_progress(f"Something went wrong. Please try again.")
    loop.close()

    elapsed = time.time() - start_time
    progress_container.update(label=f"Done! {len(all_comments)} comments in {elapsed:.1f}s", state="complete")

    # Results
    if all_comments:
        st.markdown("---")
        st.markdown("### Results")

        # Summary metrics
        top_level = [c for c in all_comments if c.get("threadingDepth", 0) == 0]
        replies = [c for c in all_comments if c.get("threadingDepth", 0) > 0]
        total_likes = sum(int(c.get("likesCount", 0) or 0) for c in all_comments)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Comments", fmt_num(len(all_comments)))
        m2.metric("Top-level", fmt_num(len(top_level)))
        m3.metric("Replies", fmt_num(len(replies)))
        m4.metric("Total Likes", fmt_num(total_likes))

        # Data table
        import pandas as pd
        df = pd.DataFrame(all_comments)
        display_cols = ["profileName", "text", "likesCount", "commentsCount", "date", "threadingDepth"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=400)

        # Download buttons
        st.markdown("### Download")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "📥 Download CSV",
                data=export_csv_bytes(all_comments),
                file_name="facebook_comments.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "📥 Download JSON",
                data=export_json_bytes(all_comments),
                file_name="facebook_comments.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("No comments were found. The post may have no comments or require different cookies.")

elif scrape_btn:
    st.warning("Please enter at least one Facebook URL above.")
