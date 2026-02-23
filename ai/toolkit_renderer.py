"""
Toolkit Report Renderer
========================
Renders the 10-tab toolkit analysis report using raw markdown
responses from NotebookLM. Each tab shows the full analysis
via st.markdown(), with optional hero metrics extracted via
lightweight regex for key summary cards.
"""

import re
import streamlit as st

from ai.toolkit_queries import TOOLKIT_TAB_CONFIG


def render_toolkit_report(toolkit_results: dict[str, str], topic: str):
    """Render the full toolkit report as a tabbed interface.

    Args:
        toolkit_results: Dict mapping query_id → raw markdown response.
        topic: The research topic (for display).
    """
    if not toolkit_results or not any(toolkit_results.values()):
        st.info("No toolkit analysis results available.")
        return

    st.markdown("### Consumer Insight Report")
    st.caption(f"Deep analysis of \"{topic}\" — 10 research dimensions")

    # Inject CSS for better markdown table rendering in Streamlit dark theme
    _inject_table_css()

    # Build tabs from config, skipping empty results
    available_tabs = [
        (qid, label)
        for qid, label in TOOLKIT_TAB_CONFIG
        if toolkit_results.get(qid)
    ]

    if not available_tabs:
        st.warning("All analysis queries returned empty results.")
        return

    tab_labels = [label for _, label in available_tabs]
    tabs = st.tabs(tab_labels)

    for i, (qid, label) in enumerate(available_tabs):
        with tabs[i]:
            content = toolkit_results[qid]
            _render_tab(qid, label, content)


def _render_tab(query_id: str, label: str, content: str):
    """Render a single analysis tab with optional hero metrics + raw markdown."""
    # Try to extract hero metrics for key tabs
    hero = _extract_hero_metrics(query_id, content)
    if hero:
        _render_hero_cards(hero)

    # Render the full markdown content
    st.markdown(content, unsafe_allow_html=True)


def _extract_hero_metrics(query_id: str, content: str) -> list[dict] | None:
    """Extract lightweight summary metrics for hero cards.

    Returns a list of dicts: [{"label": str, "value": str, "color": str}]
    or None if no metrics could be extracted.
    """
    if query_id == "emotion_intent":
        return _extract_emotion_heroes(content)
    elif query_id == "tension_mapping":
        return _extract_tension_heroes(content)
    elif query_id == "comment_persona":
        return _extract_persona_heroes(content)
    elif query_id == "full_synthesis":
        return _extract_synthesis_heroes(content)
    return None


def _extract_emotion_heroes(content: str) -> list[dict] | None:
    """Extract top emotions with percentages."""
    metrics = []

    # Look for "Top 5 Emotions" section with percentage patterns
    # Matches patterns like: "1. Craving/Desire — 35%" or "- Satisfaction: 28%"
    pct_pattern = re.findall(
        r'(?:^|\n)\s*[-\d.]+[.)]*\s*\**([^—\-:*\n]+?)\**\s*[—\-:]+\s*(\d+(?:\.\d+)?)\s*%',
        content,
    )
    if pct_pattern:
        colors = ["#34D399", "#3B82F6", "#FBBF24", "#F87171", "#A78BFA"]
        for i, (emotion, pct) in enumerate(pct_pattern[:5]):
            metrics.append({
                "label": emotion.strip(),
                "value": f"{pct}%",
                "color": colors[i % len(colors)],
            })

    return metrics if metrics else None


def _extract_tension_heroes(content: str) -> list[dict] | None:
    """Extract top tension types."""
    metrics = []

    # Look for tension names with comment counts or percentages
    patterns = re.findall(
        r'(?:^|\|)\s*\**([A-Za-z\s]+vs\.?\s+[A-Za-z\s]+)\**\s*\|?\s*(\d+)',
        content,
    )
    if patterns:
        colors = ["#F87171", "#FBBF24", "#34D399", "#3B82F6", "#A78BFA"]
        for i, (tension, count) in enumerate(patterns[:4]):
            metrics.append({
                "label": tension.strip(),
                "value": f"{count} comments",
                "color": colors[i % len(colors)],
            })

    return metrics if metrics else None


def _extract_persona_heroes(content: str) -> list[dict] | None:
    """Extract persona names and proportions."""
    metrics = []

    # Match persona names like: **Night Craver** or ### Persona 1: Night Craver (~25%)
    patterns = re.findall(
        r'(?:###?\s*(?:Persona\s*\d+:?\s*)?)\**\[?([^\]]*?)\]?\**\s*(?:—\s*)?(?:\(?\~?(\d+)%?\)?)?',
        content,
    )
    if patterns:
        colors = ["#3B82F6", "#34D399", "#FBBF24", "#F87171", "#A78BFA", "#EC4899"]
        for i, (name, pct) in enumerate(patterns[:6]):
            name = name.strip().strip("*").strip()
            if not name or len(name) > 40:
                continue
            value = f"~{pct}%" if pct else ""
            metrics.append({
                "label": name,
                "value": value,
                "color": colors[i % len(colors)],
            })

    return metrics if metrics else None


def _extract_synthesis_heroes(content: str) -> list[dict] | None:
    """Extract key insight count from synthesis."""
    # Count main sections
    section_count = len(re.findall(r'^##\s+', content, re.MULTILINE))
    quick_wins = len(re.findall(r'Quick Win', content, re.IGNORECASE))
    strategic_bets = len(re.findall(r'Strategic Bet', content, re.IGNORECASE))

    metrics = []
    if section_count:
        metrics.append({"label": "Report Sections", "value": str(section_count), "color": "#3B82F6"})
    if quick_wins:
        metrics.append({"label": "Quick Wins", "value": str(quick_wins), "color": "#34D399"})
    if strategic_bets:
        metrics.append({"label": "Strategic Bets", "value": str(strategic_bets), "color": "#FBBF24"})

    return metrics if metrics else None


def _render_hero_cards(metrics: list[dict]):
    """Render hero metric cards in a row."""
    if not metrics:
        return

    # Limit to 6 cards per row
    display = metrics[:6]
    cols = st.columns(len(display))

    for i, m in enumerate(display):
        with cols[i]:
            color = m.get("color", "#3B82F6")
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);'
                f'border-radius:8px;padding:10px 14px;text-align:center">'
                f'<div style="font-size:1.2rem;font-weight:700;color:{color}">{m["value"]}</div>'
                f'<div style="font-size:0.75rem;color:#94A3B8;margin-top:2px">{m["label"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _inject_table_css():
    """Inject CSS to style markdown tables for Streamlit's dark theme."""
    st.markdown(
        """<style>
        /* Toolkit report table styling */
        .stMarkdown table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            margin: 0.5rem 0;
        }
        .stMarkdown table th {
            background: rgba(59, 130, 246, 0.08);
            color: #94A3B8;
            text-align: left;
            padding: 8px 12px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            font-weight: 600;
        }
        .stMarkdown table td {
            padding: 8px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            vertical-align: top;
        }
        .stMarkdown table tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }
        </style>""",
        unsafe_allow_html=True,
    )
