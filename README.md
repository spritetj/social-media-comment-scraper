# Social Media Comment Scraper

Extract comments from YouTube, TikTok, Facebook, and Instagram posts — free, fast, no API key required.

## Quick Start

### Run Locally

```bash
cd social_media_scraper_web
pip install -r requirements.txt
streamlit run Home.py
```

The app will open at `http://localhost:8501`.

### Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set **Main file path** to `social_media_scraper_web/Home.py`
5. Deploy — you'll get a public URL instantly

## Supported Platforms

| Platform | Method | Cloud | Local | Cookies |
|----------|--------|-------|-------|---------|
| YouTube | InnerTube API | Full | Full | Optional |
| YouTube | yt-dlp fallback | Limited | Full | Optional |
| TikTok | Direct API | Works | Full | Not needed |
| TikTok | Playwright fallback | No browser | Full | Not needed |
| Facebook | In-browser GraphQL | Needs cookies + browser | Full | Required |
| Instagram | Relay data extraction | Needs cookies + browser | Full | Recommended |

## Features

- **YouTube**: Sort by top/newest, fetch all replies, bulk URL support. Uses InnerTube API with 3-method cascade fallback.
- **TikTok**: Direct API access with browser-based fallback. Supports short URLs and full URLs.
- **Facebook**: In-browser GraphQL API — 5-15x faster than scroll-based methods. Requires cookies.
- **Instagram**: Embedded Relay data extraction with REST API pagination. Supports posts and reels.

### Common Features
- Live progress updates during scraping
- Data table with sortable columns
- Download results as CSV or JSON
- Bulk URL support (one per line)
- Summary metrics (total comments, top-level, replies, likes)

## Project Structure

```
social_media_scraper_web/
├── Home.py                     # Landing page
├── pages/
│   ├── 1_YouTube.py            # YouTube scraper UI
│   ├── 2_TikTok.py             # TikTok scraper UI
│   ├── 3_Facebook.py           # Facebook scraper UI
│   └── 4_Instagram.py          # Instagram scraper UI
├── scrapers/
│   ├── youtube.py              # YouTube InnerTube API + fallbacks
│   ├── tiktok.py               # TikTok direct API + Playwright
│   ├── facebook.py             # Facebook GraphQL API
│   └── instagram.py            # Instagram Relay extraction
├── utils/
│   └── common.py               # Shared utilities (cookies, export, rate limiting)
├── assets/
│   └── style.css               # Custom styling
├── .streamlit/
│   └── config.toml             # Theme configuration
├── requirements.txt            # Python dependencies
└── packages.txt                # System dependencies (Streamlit Cloud)
```

## Cookie Setup (Facebook & Instagram)

Facebook and Instagram require browser cookies for full access:

1. Install the [Get cookies.txt locally](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) Chrome extension
2. Log into Facebook/Instagram in your browser
3. Click the extension icon and export cookies
4. Upload the exported file in the app sidebar

## Requirements

- Python 3.10+
- For Facebook/Instagram: Playwright (`pip install playwright && python -m playwright install chromium`)

## Dependencies

Core:
- `streamlit` — Web UI framework
- `aiohttp` — Async HTTP client
- `requests` — HTTP client
- `nest-asyncio` — Async compatibility for Streamlit

Optional:
- `playwright` — Browser automation (Facebook, Instagram, TikTok fallback)
- `yt-dlp` — YouTube fallback method
