"""
Social Media Comment Scraper — Dashboard
==========================================
Space-themed dashboard with fully clickable platform cards.
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Comment Scraper",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load custom CSS
css_path = Path(__file__).parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Navigation
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
    qr_path = Path(__file__).parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)

# Dashboard header
st.markdown(
    """
    <div class="dash-header">
        <div class="dash-beacon"></div>
        <h1 class="dash-title">Comment Scraper</h1>
        <p class="dash-subtitle">Select a platform to begin extraction.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Platform cards — Row 1
# Each column has: card visual (st.markdown) + invisible overlay (st.page_link)
# CSS :has() stretches the page_link over the card for full clickability.
r1c1, r1c2 = st.columns(2, gap="medium")

with r1c1:
    st.markdown(
        """
        <div class="space-card d1">
            <div class="card-icon-ring ring-red"><span>🎬</span></div>
            <h3>YouTube</h3>
            <p>Extract comments and replies from any video.</p>
            <div class="card-meta">
                <span class="card-badge badge-open">No login needed</span>
                <span class="card-arrow">&rarr;</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_🎬_YouTube.py", label="Open YouTube")

with r1c2:
    st.markdown(
        """
        <div class="space-card d2">
            <div class="card-icon-ring ring-cyan"><span>🎵</span></div>
            <h3>TikTok</h3>
            <p>Video comments and reply threads.</p>
            <div class="card-meta">
                <span class="card-badge badge-open">No login needed</span>
                <span class="card-arrow">&rarr;</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/2_🎵_TikTok.py", label="Open TikTok")

# Platform cards — Row 2
r2c1, r2c2 = st.columns(2, gap="medium")

with r2c1:
    st.markdown(
        """
        <div class="space-card d3">
            <div class="card-icon-ring ring-blue"><span>📘</span></div>
            <h3>Facebook</h3>
            <p>Scrape comments from posts, reels, and videos.</p>
            <div class="card-meta">
                <span class="card-badge badge-auth">Cookies required</span>
                <span class="card-arrow">&rarr;</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/3_📘_Facebook.py", label="Open Facebook")

with r2c2:
    st.markdown(
        """
        <div class="space-card d4">
            <div class="card-icon-ring ring-violet"><span>📷</span></div>
            <h3>Instagram</h3>
            <p>Post and reel comments with replies.</p>
            <div class="card-meta">
                <span class="card-badge badge-auth">Cookies optional</span>
                <span class="card-arrow">&rarr;</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/4_📷_Instagram.py", label="Open Instagram")

# Footer
st.markdown(
    '<div class="platform-footer">Comment Scraper &mdash; All platforms supported</div>',
    unsafe_allow_html=True,
)
