"""
Feature gating — check access and show upgrade prompts.
"""

import streamlit as st

from config.tiers import TIERS, FEATURE_INFO


def get_current_tier() -> str:
    """Get the current user's tier. Session-based for MVP."""
    return st.session_state.get("user_tier", "free")


def check_feature(feature: str) -> bool:
    """Check if a feature is available in the current tier.
    Shows upgrade prompt if not available. Returns True if accessible."""
    tier_name = get_current_tier()
    tier = TIERS.get(tier_name, TIERS["free"])
    value = tier["features"].get(feature)

    if value is None:
        return False

    # Boolean features
    if isinstance(value, bool):
        if not value:
            _show_upgrade_prompt(feature)
            return False
        return True

    # Numeric limits (0 = disabled)
    if isinstance(value, (int, float)) and value <= 0:
        _show_upgrade_prompt(feature)
        return False

    return True


def check_url_limit(current_count: int) -> bool:
    """Check if the user is within their URL scraping limit."""
    tier_name = get_current_tier()
    limit = TIERS[tier_name]["features"].get("urls_per_session", 5)

    if current_count >= limit:
        st.warning(
            f"You've reached the {limit} URL limit for the {tier_name.title()} tier. "
            f"Upgrade to Pro for up to {TIERS['pro']['features']['urls_per_session']} URLs per session."
        )
        return False

    return True


def _show_upgrade_prompt(feature: str):
    """Show an upgrade prompt for a locked feature."""
    info = FEATURE_INFO.get(feature, {})
    name = info.get("name", feature.replace("_", " ").title())
    desc = info.get("description", "")

    st.markdown(
        f"""
        <div style="background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.2);
        border-radius:12px;padding:1.25rem;text-align:center;margin:1rem 0">
            <div style="font-size:1.5rem;margin-bottom:0.5rem">🔒</div>
            <div style="font-size:1rem;font-weight:600;color:#F1F5F9;margin-bottom:0.3rem">
                {name}
            </div>
            <div style="font-size:0.85rem;color:#94A3B8;margin-bottom:0.75rem">
                {desc}
            </div>
            <div style="font-size:0.8rem;color:#60A5FA">
                Available in Pro ($29/month)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
