"""
AI Results Rendering
=====================
Renders structured AI analysis results using Streamlit components.
Each analysis type gets purpose-built visual treatment consistent
with the app's dark SaaS design system.
"""

import json
import streamlit as st


# ---------------------------------------------------------------------------
# Colour helpers (map to CSS variables)
# ---------------------------------------------------------------------------

_SEVERITY_COLOURS = {
    "high": "#EF4444",      # red
    "medium": "#F59E0B",    # amber
    "low": "#34D399",       # green
    "critical": "#DC2626",  # dark red
}

_INTENT_COLOURS = {
    "actively_buying": "#34D399",
    "considering": "#3B82F6",
    "satisfied_customers": "#34D399",
    "dissatisfied_customers": "#F59E0B",
    "churning": "#EF4444",
}


def _badge(text: str, colour: str) -> str:
    """Return an inline HTML badge."""
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:6px;'
        f"font-size:0.75rem;font-weight:600;letter-spacing:0.03em;"
        f"background:{colour}18;color:{colour};border:1px solid {colour}33;"
        f'font-family:Inter,sans-serif">{text}</span>'
    )


def _card_open(title: str = "", accent: str = "#3B82F6") -> str:
    """Open an HTML card container."""
    header = f'<h4 style="margin:0 0 0.6rem 0;font-size:0.95rem;color:#F1F5F9">{title}</h4>' if title else ""
    return (
        f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);'
        f"border-radius:12px;padding:1.25rem;margin-bottom:1rem;"
        f'border-top:3px solid {accent}">'
        f"{header}"
    )


def _card_close() -> str:
    return "</div>"


def _blockquote(text: str) -> str:
    return (
        f'<blockquote style="border-left:3px solid rgba(255,255,255,0.12);'
        f"padding-left:0.8rem;margin:0.4rem 0;color:#94A3B8;"
        f'font-size:0.85rem;font-style:italic">{text}</blockquote>'
    )


# ---------------------------------------------------------------------------
# Per-type renderers
# ---------------------------------------------------------------------------

def _render_pain_points(results: dict) -> None:
    points = results.get("pain_points", [])
    summary = results.get("summary", "")
    if summary:
        st.markdown(f"**Summary:** {summary}")
    for pt in points:
        severity = pt.get("severity", "medium")
        colour = _SEVERITY_COLOURS.get(severity, "#94A3B8")
        html = _card_open(pt.get("issue", "Unknown issue"), colour)
        html += f'<p style="margin:0.3rem 0;font-size:0.85rem;color:#94A3B8">'
        html += f'{_badge(severity.upper(), colour)} '
        html += f'{_badge(pt.get("category", "other"), "#3B82F6")} '
        html += f'Mentioned {pt.get("frequency", "?")} time(s)</p>'
        if pt.get("impact_summary"):
            html += f'<p style="font-size:0.85rem;color:#CBD5E1;margin:0.5rem 0">{pt["impact_summary"]}</p>'
        for q in pt.get("example_quotes", [])[:3]:
            html += _blockquote(q)
        html += _card_close()
        st.markdown(html, unsafe_allow_html=True)


def _render_feature_requests(results: dict) -> None:
    requests = results.get("feature_requests", [])
    summary = results.get("summary", "")
    if summary:
        st.markdown(f"**Summary:** {summary}")
    for fr in requests:
        urgency = fr.get("urgency", "medium")
        colour = _SEVERITY_COLOURS.get(urgency, "#3B82F6")
        html = _card_open(fr.get("feature", "Unknown feature"), colour)
        html += f'<p style="margin:0.3rem 0;font-size:0.85rem;color:#94A3B8">'
        html += f'{_badge(urgency.upper(), colour)} '
        html += f'Requested {fr.get("request_count", "?")} time(s)</p>'
        segments = fr.get("user_segments", [])
        if segments:
            html += '<p style="margin:0.4rem 0;font-size:0.85rem;color:#94A3B8">Segments: '
            html += " ".join(_badge(s, "#8B5CF6") for s in segments)
            html += "</p>"
        if fr.get("potential_impact"):
            html += f'<p style="font-size:0.85rem;color:#CBD5E1;margin:0.5rem 0">Impact: {fr["potential_impact"]}</p>'
        for q in fr.get("example_quotes", [])[:2]:
            html += _blockquote(q)
        html += _card_close()
        st.markdown(html, unsafe_allow_html=True)


def _render_competitive_intel(results: dict) -> None:
    summary = results.get("summary", "")
    if summary:
        st.markdown(f"**Summary:** {summary}")
    competitors = results.get("competitors", [])
    for comp in competitors:
        sentiment = comp.get("sentiment", "neutral")
        sent_colour = {"positive": "#34D399", "negative": "#EF4444", "mixed": "#F59E0B"}.get(sentiment, "#94A3B8")
        html = _card_open(comp.get("name", "Unknown"), sent_colour)
        html += f'<p style="margin:0.3rem 0;font-size:0.85rem;color:#94A3B8">'
        html += f'{_badge(sentiment, sent_colour)} '
        html += f'{comp.get("mention_count", 0)} mentions</p>'
        adv = comp.get("advantages_cited", [])
        if adv:
            html += '<p style="font-size:0.85rem;color:#34D399;margin:0.4rem 0">Advantages: ' + ", ".join(adv) + "</p>"
        disadv = comp.get("disadvantages_cited", [])
        if disadv:
            html += '<p style="font-size:0.85rem;color:#EF4444;margin:0.4rem 0">Disadvantages: ' + ", ".join(disadv) + "</p>"
        for q in comp.get("example_quotes", [])[:2]:
            html += _blockquote(q)
        html += _card_close()
        st.markdown(html, unsafe_allow_html=True)
    gaps = results.get("positioning_gaps", [])
    if gaps:
        st.markdown("#### Positioning Gaps")
        for g in gaps:
            if isinstance(g, dict):
                html = _card_open(g.get("gap", ""), "#F59E0B")
                html += f'<p style="font-size:0.85rem;color:#CBD5E1">{g.get("opportunity", "")}</p>'
                html += _card_close()
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.markdown(f"- {g}")


def _render_purchase_intent(results: dict) -> None:
    summary = results.get("summary", "")
    if summary:
        st.markdown(f"**Summary:** {summary}")
    signals = results.get("intent_signals", {})
    if signals:
        cols = st.columns(len(signals))
        for col, (key, data) in zip(cols, signals.items()):
            label = key.replace("_", " ").title()
            colour = _INTENT_COLOURS.get(key, "#3B82F6")
            count = data.get("count", 0) if isinstance(data, dict) else data
            with col:
                html = _card_open("", colour)
                html += f'<p style="font-size:2rem;font-weight:700;color:{colour};margin:0;text-align:center">{count}</p>'
                html += f'<p style="font-size:0.75rem;color:#94A3B8;text-align:center;margin:0.3rem 0 0">{label}</p>'
                html += _card_close()
                st.markdown(html, unsafe_allow_html=True)
    funnel = results.get("funnel_summary", {})
    if funnel:
        drivers = funnel.get("key_drivers", [])
        blockers = funnel.get("key_blockers", [])
        d_col, b_col = st.columns(2)
        with d_col:
            if drivers:
                st.markdown("**Key Drivers**")
                for d in drivers:
                    st.markdown(f"- {d}")
        with b_col:
            if blockers:
                st.markdown("**Key Blockers**")
                for b in blockers:
                    st.markdown(f"- {b}")


def _render_customer_personas(results: dict) -> None:
    summary = results.get("summary", "")
    if summary:
        st.markdown(f"**Summary:** {summary}")
    personas = results.get("personas", [])
    for persona in personas:
        pct = persona.get("estimated_percentage", "?")
        html = _card_open(f'{persona.get("name", "Unknown")} ({pct}%)', "#8B5CF6")
        html += f'<p style="font-size:0.88rem;color:#CBD5E1;margin:0.3rem 0">{persona.get("description", "")}</p>'
        needs = persona.get("needs", [])
        if needs:
            html += '<p style="font-size:0.85rem;color:#94A3B8;margin:0.4rem 0"><strong>Needs:</strong> ' + ", ".join(needs) + "</p>"
        pains = persona.get("pain_points", [])
        if pains:
            html += '<p style="font-size:0.85rem;color:#94A3B8;margin:0.4rem 0"><strong>Pain points:</strong> ' + ", ".join(pains) + "</p>"
        behaviors = persona.get("behaviors", [])
        if behaviors:
            html += '<p style="font-size:0.85rem;color:#94A3B8;margin:0.4rem 0"><strong>Behaviors:</strong> ' + ", ".join(behaviors) + "</p>"
        if persona.get("recommended_approach"):
            html += f'<p style="font-size:0.85rem;color:#3B82F6;margin:0.5rem 0"><strong>Recommended approach:</strong> {persona["recommended_approach"]}</p>'
        for q in persona.get("typical_quotes", [])[:2]:
            html += _blockquote(q)
        html += _card_close()
        st.markdown(html, unsafe_allow_html=True)


def _render_full_report(results: dict) -> None:
    executive = results.get("executive_summary", "")
    if executive:
        st.markdown(f"**Executive Summary:** {executive}")
    tabs = st.tabs(["Pain Points", "Features", "Competition", "Intent", "Segments", "Recommendations"])
    with tabs[0]:
        _render_pain_points(results)
    with tabs[1]:
        _render_feature_requests(results)
    with tabs[2]:
        landscape = results.get("competitive_landscape", {})
        competitors = landscape.get("competitors_mentioned", [])
        for comp in competitors:
            sentiment = comp.get("sentiment", "neutral")
            sent_colour = {"positive": "#34D399", "negative": "#EF4444", "mixed": "#F59E0B"}.get(sentiment, "#94A3B8")
            html = _card_open(comp.get("name", "Unknown"), sent_colour)
            html += f'{_badge(sentiment, sent_colour)} {comp.get("mention_count", 0)} mentions'
            html += _card_close()
            st.markdown(html, unsafe_allow_html=True)
        gaps = landscape.get("positioning_gaps", [])
        for g in gaps:
            st.markdown(f"- {g}")
    with tabs[3]:
        intent = results.get("purchase_intent", {})
        if intent:
            cols = st.columns(5)
            labels = ["Actively Buying", "Considering", "Satisfied", "Dissatisfied", "Churning"]
            keys = ["actively_buying", "considering", "satisfied", "dissatisfied", "churning"]
            colours = ["#34D399", "#3B82F6", "#34D399", "#F59E0B", "#EF4444"]
            for col, label, key, colour in zip(cols, labels, keys, colours):
                with col:
                    count = intent.get(key, 0)
                    html = _card_open("", colour)
                    html += f'<p style="font-size:2rem;font-weight:700;color:{colour};margin:0;text-align:center">{count}</p>'
                    html += f'<p style="font-size:0.72rem;color:#94A3B8;text-align:center;margin:0.3rem 0 0">{label}</p>'
                    html += _card_close()
                    st.markdown(html, unsafe_allow_html=True)
    with tabs[4]:
        segments = results.get("customer_segments", [])
        for seg in segments:
            html = _card_open(f'{seg.get("name", "Unknown")} ({seg.get("estimated_percentage", "?")}%)', "#8B5CF6")
            needs = seg.get("key_needs", [])
            if needs:
                html += '<p style="font-size:0.85rem;color:#94A3B8">Needs: ' + ", ".join(needs) + "</p>"
            pains = seg.get("key_pain_points", [])
            if pains:
                html += '<p style="font-size:0.85rem;color:#94A3B8">Pain points: ' + ", ".join(pains) + "</p>"
            html += _card_close()
            st.markdown(html, unsafe_allow_html=True)
    with tabs[5]:
        recs = results.get("recommendations", [])
        for rec in recs:
            priority = rec.get("priority", "medium")
            colour = _SEVERITY_COLOURS.get(priority, "#3B82F6")
            html = _card_open(rec.get("recommendation", ""), colour)
            html += f'{_badge(priority.upper() + " PRIORITY", colour)}'
            html += f'<p style="font-size:0.85rem;color:#CBD5E1;margin:0.5rem 0">{rec.get("rationale", "")}</p>'
            html += _card_close()
            st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_RENDERERS = {
    "pain_points": _render_pain_points,
    "feature_requests": _render_feature_requests,
    "competitive_intel": _render_competitive_intel,
    "purchase_intent": _render_purchase_intent,
    "customer_personas": _render_customer_personas,
    "full_market_research": _render_full_report,
}


def render_ai_results(results: dict | str, analysis_type: str) -> None:
    """Render AI analysis results with type-appropriate visualisation."""
    if isinstance(results, str):
        st.markdown(results)
        return
    renderer = _RENDERERS.get(analysis_type)
    if renderer:
        renderer(results)
    else:
        st.json(results)


def render_ai_download(results: dict | str, analysis_type: str) -> None:
    """Provide a download button for the AI analysis results as JSON."""
    if isinstance(results, str):
        data = results.encode("utf-8")
        mime = "text/plain"
        ext = "txt"
    else:
        data = json.dumps(results, indent=2, ensure_ascii=False).encode("utf-8")
        mime = "application/json"
        ext = "json"
    st.download_button(
        label="Download AI Report",
        data=data,
        file_name=f"ai_{analysis_type}_report.{ext}",
        mime=mime,
        use_container_width=True,
    )
