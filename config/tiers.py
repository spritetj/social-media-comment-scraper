"""
Tier definitions — Free vs Pro feature access.
"""

TIERS = {
    "free": {
        "name": "Free",
        "price": 0,
        "features": {
            "per_platform_scraping": True,
            "urls_per_session": 5,
            "basic_analysis": True,
            "advanced_analysis": False,
            "ai_analysis": False,
            "one_search": False,
            "one_search_daily": 0,
            "export_csv": True,
            "export_json": True,
            "export_pdf": False,
        },
    },
    "pro": {
        "name": "Pro",
        "price": 29,
        "features": {
            "per_platform_scraping": True,
            "urls_per_session": 50,
            "basic_analysis": True,
            "advanced_analysis": True,
            "ai_analysis": True,
            "one_search": True,
            "one_search_daily": 5,
            "export_csv": True,
            "export_json": True,
            "export_pdf": True,
        },
    },
}

# Feature display names and descriptions
FEATURE_INFO = {
    "per_platform_scraping": {
        "name": "Per-Platform Scraping",
        "description": "Paste URLs and scrape comments from any platform",
    },
    "urls_per_session": {
        "name": "URLs per Session",
        "description": "Maximum URLs you can scrape in one session",
    },
    "basic_analysis": {
        "name": "Basic Analysis",
        "description": "Sentiment analysis and keyword extraction",
    },
    "advanced_analysis": {
        "name": "Advanced Analysis",
        "description": "Topic modeling, temporal patterns, engagement metrics",
    },
    "ai_analysis": {
        "name": "AI-Powered Analysis",
        "description": "Deep insights using Claude, ChatGPT, or Gemini (BYOK)",
    },
    "one_search": {
        "name": "One Search",
        "description": "Multi-platform research from a single topic query",
    },
    "one_search_daily": {
        "name": "One Search Daily Limit",
        "description": "Number of One Search queries per day",
    },
    "export_csv": {
        "name": "Export CSV",
        "description": "Download results as CSV spreadsheet",
    },
    "export_json": {
        "name": "Export JSON",
        "description": "Download results as JSON data",
    },
    "export_pdf": {
        "name": "Export PDF Report",
        "description": "Download a formatted PDF research report",
    },
}


def get_tier(tier_name: str = "free") -> dict:
    """Get tier configuration."""
    return TIERS.get(tier_name, TIERS["free"])


def get_feature_limit(feature: str, tier_name: str = "free"):
    """Get the limit/access for a specific feature in a tier."""
    tier = get_tier(tier_name)
    return tier["features"].get(feature)
