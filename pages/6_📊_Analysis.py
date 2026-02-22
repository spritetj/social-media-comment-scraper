"""
Standalone Analysis Page — upload CSV/JSON or analyze last scrape.
"""

import streamlit as st
import json
import csv
import io
from pathlib import Path

st.set_page_config(
    page_title="Analysis — Comment Scraper",
    page_icon="📊",
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
st.markdown('<div class="page-header"><h1>Analysis</h1></div>', unsafe_allow_html=True)
st.markdown('<p class="page-desc">Upload exported comments or analyze your last scrape.</p>', unsafe_allow_html=True)

# Data source tabs
tab_scrape, tab_upload = st.tabs(["Last Scrape", "Upload File"])

comments_to_analyze = None

with tab_scrape:
    last_scrape = st.session_state.get("last_scrape")
    if last_scrape and last_scrape.get("comments"):
        comments_to_analyze = last_scrape["comments"]
        st.success(
            f"Found {last_scrape['count']} comments from {last_scrape['platform'].title()} "
            f"in session"
        )
    else:
        st.info(
            "No recent scrape data found. Go to a platform page to scrape comments first, "
            "or upload a file below."
        )

with tab_upload:
    uploaded = st.file_uploader(
        "Upload previously exported CSV or JSON",
        type=["csv", "json"],
        help="Upload a file exported from this tool (Clean format recommended)",
    )

    if uploaded:
        try:
            content = uploaded.read().decode("utf-8")
            name = uploaded.name.lower()

            if name.endswith(".json"):
                data = json.loads(content)
                if isinstance(data, list) and data:
                    comments_to_analyze = data
                    st.success(f"Loaded {len(data)} comments from JSON")
                else:
                    st.error("JSON file should contain a list of comment objects")

            elif name.endswith(".csv"):
                reader = csv.DictReader(io.StringIO(content))
                data = list(reader)
                if data:
                    # Convert numeric fields
                    for row in data:
                        for key in ("likes", "replies"):
                            if key in row:
                                try:
                                    row[key] = int(float(row[key]))
                                except (ValueError, TypeError):
                                    row[key] = 0
                        if "is_reply" in row:
                            row["is_reply"] = row["is_reply"].lower() in ("true", "1", "yes")
                    comments_to_analyze = data
                    st.success(f"Loaded {len(data)} comments from CSV")
                else:
                    st.error("CSV file is empty")

        except Exception as e:
            st.error(f"Failed to parse file: {e}")

# Run analysis
if comments_to_analyze and len(comments_to_analyze) >= 10:
    try:
        from analysis.pipeline import run_full_analysis
        from utils.analysis_ui import render_analysis_dashboard

        with st.spinner("Running analysis..."):
            analysis = run_full_analysis(comments_to_analyze)
        render_analysis_dashboard(analysis)
    except ImportError as e:
        st.error(f"Analysis modules not available: {e}")
        st.info("Make sure all analysis dependencies are installed: `pip install -r requirements.txt`")

elif comments_to_analyze:
    st.warning(f"Only {len(comments_to_analyze)} comments found. Need at least 10 for analysis.")
