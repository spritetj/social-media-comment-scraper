"""
Social Media Comment Scraper — Landing Page
=============================================
Streamlit multi-page app entry point.
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

# Navigation bar
nav_cols = st.columns([1, 1, 1, 1, 1, 1])
with nav_cols[0]:
    st.page_link("Home.py", label="Home", icon="🏠")
with nav_cols[1]:
    st.page_link("pages/1_🎬_YouTube.py", label="YouTube", icon="🎬")
with nav_cols[2]:
    st.page_link("pages/2_🎵_TikTok.py", label="TikTok", icon="🎵")
with nav_cols[3]:
    st.page_link("pages/3_📘_Facebook.py", label="Facebook", icon="📘")
with nav_cols[4]:
    st.page_link("pages/4_📷_Instagram.py", label="Instagram", icon="📷")
with nav_cols[5]:
    qr_path = Path(__file__).parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("☕ Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)

# Hero section — centered
st.markdown(
    """
    <div class="hero-section">
        <p class="hero-eyebrow">Social Media Toolkit</p>
        <h1 class="hero-title">Comment Scraper.</h1>
        <p class="hero-subtitle">Extract comments from any platform.<br>Fast, simple, powerful.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Platform cards in 2x2 grid
col1, col2 = st.columns(2, gap="medium")

with col1:
    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon yt">🎬</div>
            <h3>YouTube</h3>
            <p>Comments and replies from any video.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_🎬_YouTube.py", label="Explore YouTube  →", icon=None)

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon fb">📘</div>
            <h3>Facebook</h3>
            <p>Posts, reels, and video comments.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/3_📘_Facebook.py", label="Explore Facebook  →", icon=None)

with col2:
    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon tt">🎵</div>
            <h3>TikTok</h3>
            <p>Video comments and reply threads.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/2_🎵_TikTok.py", label="Explore TikTok  →", icon=None)

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon ig">📷</div>
            <h3>Instagram</h3>
            <p>Post and reel comments with replies.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/4_📷_Instagram.py", label="Explore Instagram  →", icon=None)

# Footer
st.markdown(
    '<div class="pro-footer">Built with care. All platforms supported.</div>',
    unsafe_allow_html=True,
)
