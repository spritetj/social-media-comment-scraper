"""
Social Media Comment Scraper — Landing Page
=============================================
Streamlit multi-page app entry point.
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Social Media Comment Scraper",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load custom CSS
css_path = Path(__file__).parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### 💬 Comment Scraper")
    st.markdown("---")
    st.markdown("Select a platform from the sidebar to start scraping comments.")
    st.markdown("")
    st.markdown(
        "**Supported Platforms:**\n"
        "- 🎬 YouTube\n"
        "- 🎵 TikTok\n"
        "- 📘 Facebook\n"
        "- 📷 Instagram"
    )
    st.markdown("---")
    st.caption("Free & open source. No API key needed.")

# Hero section
st.markdown("")
st.markdown(
    '<h1 class="hero-title">Social Media Comment Scraper</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    "**Extract comments from any social media post — free, fast, no API key required.**"
)
st.markdown("---")

# Platform cards in 2x2 grid
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div class="platform-card">
            <h3>🎬 YouTube</h3>
            <p>Extract comments & replies from any YouTube video. Uses YouTube's InnerTube API with multi-method fallback.</p>
            <p><strong>Features:</strong> Sort by top/newest, get replies, bulk URL support</p>
            <p><em>Works on cloud & locally — no browser needed</em></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping YouTube →", key="yt_btn", use_container_width=True):
        st.switch_page("pages/1_🎬_YouTube.py")

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <h3>📘 Facebook</h3>
            <p>Scrape comments from Facebook posts, reels, and videos using in-browser GraphQL API.</p>
            <p><strong>Features:</strong> All comment types, nested replies, post captions</p>
            <p><em>Requires cookies — best run locally</em></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping Facebook →", key="fb_btn", use_container_width=True):
        st.switch_page("pages/3_📘_Facebook.py")

with col2:
    st.markdown(
        """
        <div class="platform-card">
            <h3>🎵 TikTok</h3>
            <p>Extract comments & replies from TikTok videos. Direct API access with browser-based fallback.</p>
            <p><strong>Features:</strong> Video captions, reply threads, parallel workers</p>
            <p><em>Works on cloud & locally</em></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping TikTok →", key="tt_btn", use_container_width=True):
        st.switch_page("pages/2_🎵_TikTok.py")

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <h3>📷 Instagram</h3>
            <p>Scrape comments from Instagram posts and reels. Uses embedded Relay data extraction.</p>
            <p><strong>Features:</strong> Nested replies, captions, concurrent workers</p>
            <p><em>Requires cookies — best run locally</em></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping Instagram →", key="ig_btn", use_container_width=True):
        st.switch_page("pages/4_📷_Instagram.py")

# Cloud vs Local feature matrix
st.markdown("---")
st.markdown("### Cloud vs Local Support")

matrix_data = {
    "Platform": ["YouTube (InnerTube API)", "YouTube (yt-dlp fallback)", "TikTok (Direct API)", "TikTok (Playwright)", "Facebook", "Instagram"],
    "Streamlit Cloud": ["✅ Full", "⚠️ Limited", "✅ Works", "❌ No browser", "⚠️ Needs cookies + browser", "⚠️ Needs cookies + browser"],
    "Local": ["✅ Full", "✅ Full", "✅ Full", "✅ Full", "✅ Full", "✅ Full"],
}
st.table(matrix_data)

# Footer
st.markdown("---")
st.markdown(
    "Runs 100% free — No API key needed. "
    "YouTube & TikTok work via direct HTTP API. "
    "Facebook & Instagram require Playwright + cookies (best run locally)."
)
