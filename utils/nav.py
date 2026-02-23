"""
Shared navigation bar — single source of truth for all pages.
"""

import streamlit as st


# All pages in display order
PAGES = [
    ("Home.py", "Home"),
    ("pages/1_🎬_YouTube.py", "YouTube"),
    ("pages/2_🎵_TikTok.py", "TikTok"),
    ("pages/3_📘_Facebook.py", "Facebook"),
    ("pages/4_📷_Instagram.py", "Instagram"),
    ("pages/5_🔍_One_Search.py", "One Search"),
    ("pages/7_⚙️_Settings.py", "Settings"),
]


def render_nav():
    """Render the horizontal navigation bar used on every page."""
    cols = st.columns(len(PAGES))
    for col, (path, label) in zip(cols, PAGES):
        with col:
            st.page_link(path, label=label)
    st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)
