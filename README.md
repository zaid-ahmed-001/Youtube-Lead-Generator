# YouTube Creator Scraper & Analyzer

A comprehensive Python-based tool for scraping YouTube creator data and analyzing it using AI (Google Gemini). Features include profile analysis, audience insights, content quality scoring, sponsorship evaluation, and automated continuous scraping.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Usage Modes](#usage-modes)
   - [Manual Mode](#manual-mode)
   - [Auto-Run Mode](#auto-run-mode)
   - [Web Viewer](#web-viewer)
6. [Configuration](#configuration)
7. [Database Schema](#database-schema)
8. [Architecture](#architecture)
9. [API Reference](#api-reference)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This application scrapes YouTube creator profiles, extracts video data, and uses Google Gemini AI to analyze:
- Upload frequency and channel health
- Category distribution and content styles
- Social media presence
- Channel statistics and growth patterns
- Video transcripts, comments, and thumbnails
- Audience demographics and engagement
- Brand associations and sponsorship readiness

All data is stored in SQLite with full historical tracking.

---

## Features

### Core Analysis
- ✅ **Creator Profile**: Niche detection, content style classification
- ✅ **Audience Analysis**: Demographics, interests, buying intent
- ✅ **Brand Detection**: Associated brands, products, technologies
- ✅ **Quality Scoring**: Production quality, consistency, originality (0-10 scale)
- ✅ **Sponsorship Evaluation**: Readiness score, existing sponsorships
- ✅ **Activity Tracking**: Upload frequency, consistency, channel health status
- ✅ **Benchmarking**: Head-to-head creator comparisons

### Deep Analysis (Optional)
- 📹 **Transcript Analysis**: Topics, CTAs, sponsor pitches
- 💬 **Sentiment Analysis**: Comment themes, audience questions
- 🖼️ **Thumbnail Analysis**: Design quality, clickbait scoring (Vision AI)

### Automation
- 🤖 **Auto-Run Mode**: Continuous keyword-based scraping
- 🔄 **Smart Re-scraping**: Time-based duplicate prevention
- 📊 **Historical Tracking**: Every scrape saved with timestamp
- ⚡ **Rate Limiting**: Configurable delays to protect API quota

### Web Interface
- 🌐 **Beautiful Dashboard**: View all scraped data in a web browser
- 🔍 **Search & Filter**: Find channels by name, niche, or metrics
- 📈 **Statistics**: Total channels, runs, videos at a glance
- 📋 **Detailed Views**: Click any channel for full analysis

---

## Installation

### Prerequisites
- Python 3.8+
- YouTube Data API v3 key ([Get one here](https://console.cloud.google.com/apis/credentials))
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

### Setup

```bash
# Clone or download the project
cd Library

# Install dependencies
pip install -r requirements.txt

# Configure API keys
# Edit config.py and add your keys:
# API_KEY = "your_youtube_api_key"
# GEMINI_API_KEY = "your_gemini_api_key"
```

**Dependencies** (`requirements.txt`):
```
google-api-python-client
pandas
python-dateutil
playwright
youtube-transcript-api
requests
pydantic
flask
```

---

## Quick Start

### 1. Manual Analysis (Single Channel)
```bash
python main.py
```
Follow the interactive prompts to:
- Search by keyword or enter channel handle directly
- Choose deep analysis options
- Optionally benchmark against competitors

### 2. Automated Scraping (Continuous)
```bash
# Configure keywords in auto_config.py first
python auto_run.py
```
Runs continuously until you press `Ctrl+C`

### 3. View Data (Web Interface)
```bash
python simple_viewer.py
# Open http://localhost:5000 in your browser
```

---

## Usage Modes

### Manual Mode

**Script**: `main.py`  
**Use Case**: Deep-dive analysis of specific channels

#### Interactive Options

1. **Search Mode**:
   - Enter keywords (comma-separated)
   - Choose sort order (popular/new/featured)
   - Select region (optional)
   - Pick from search results

2. **Direct Handle Mode**:
   - Enter channel handle directly (e.g., `@LinusTechTips`)

3. **Analysis Options**:
   - Deep content analysis (transcripts, comments, thumbnails)
   - Competitor benchmarking

#### Example Session
```
Search by keyword or enter direct handle? (search/handle): search
Enter keyword(s) separated by commas: tech review, gadgets
Sort by (popular/new/featured): popular
Enter region (e.g., usa, india) or leave blank for global: us
Enter top N channels to fetch (default 5): 10

Channels found:
[1] Marques Brownlee (@MKBHD) - 18,500,000 subs | 3,250,000,000 views
[2] Linus Tech Tips (@LinusTechTips) - 16,900,000 subs | 8,100,000,000 views
...

Enter the number of the channel to analyze: 1

--- Creator Profile ---
Primary Niche: Technology Reviews
Content Styles: Review, Tutorial, Unboxing
...
```

---

### Auto-Run Mode

**Script**: `auto_run.py`  
**Config**: `auto_config.py`  
**Use Case**: Continuous monitoring, market research, trend tracking

#### Configuration

Edit `auto_config.py`:

```python
# What to search for
KEYWORDS = ["tech review", "programming tutorial", "gaming"]

# Geographic filter (None = global)
REGION_CODE = "US"  # or None, "IN", "GB", "CA", etc.

# Sort order
SORT_ORDER = "viewCount"  # or "relevance", "date"

# How many channels per search cycle
MAX_CHANNELS_PER_SEARCH = 10

# Re-scrape only if older than X hours
RESCRAPE_THRESHOLD_HOURS = 168  # 7 days

# Rate limiting (seconds between channels)
DELAY_BETWEEN_CHANNELS = 3

# Deep analysis (expensive on API quota)
DO_DEEP_ANALYSIS = False
DEEP_ANALYSIS_LIMIT = 2
```

#### How It Works

1. **Search** → Finds channels matching keywords
2. **Filter** → Applies region and sort order
3. **Check Database** → Skips recently scraped channels
4. **Analyze** → Runs full AI analysis on new/old channels
5. **Save** → Stores results with timestamp
6. **Repeat** → Continuous loop until `Ctrl+C`

#### Output Example
```
╔═══════════════════════════════════════════════════════════════════╗
║            AUTO-RUN MODE - CONTINUOUS SCRAPING                    ║
╚═══════════════════════════════════════════════════════════════════╝

📋 Configuration:
   Keywords: ['tech review']
   Region: US
   Sort: viewCount
   Max channels per search: 10
   Re-scrape threshold: 168 hours

🔍 Searching for channels...
✓ Found 10 channels

[1/10] TechReviewer (@techreviewer) - ⏭️  Skipped (scraped recently)
[2/10] GadgetGuru (@gadgetguru) - Processing...
✓ Channel saved!

📊 Batch Summary:
   Processed: 8 | Skipped: 2 | Errors: 0
```

#### Use Cases

**Daily Trend Monitoring**:
```python
KEYWORDS = ["tech news"]
RESCRAPE_THRESHOLD_HOURS = 24
SORT_ORDER = "date"
```

**Competitor Tracking**:
```python
KEYWORDS = ["your niche"]
REGION_CODE = "US"
RESCRAPE_THRESHOLD_HOURS = 168  # Weekly
```

**Market Research**:
```python
KEYWORDS = ["product category"]
MAX_CHANNELS_PER_SEARCH = 50
RESCRAPE_THRESHOLD_HOURS = 720  # Monthly
```

---

### Web Viewer

**Script**: `simple_viewer.py`  
**URL**: `http://localhost:5000`  
**Use Case**: Browse and explore scraped data

#### Features

- **📊 Dashboard**: Stats cards (channels, runs, videos)
- **🔍 Search**: Real-time search by name or niche
- **📋 Table View**: Sortable columns with all key metrics
- **🎨 Color Badges**: Activity status (Excellent/Healthy/Active/Dormant)
- **📱 Responsive**: Works on desktop and mobile

#### Quick Start
```bash
python simple_viewer.py
# Open http://localhost:5000
```

#### API Endpoints

All data accessible via REST API:

```bash
# Get statistics
curl http://localhost:5000/api/data

# Response:
{
  "stats": {
    "total_channels": 42,
    "total_runs": 15,
    "total_videos": 840,
    "latest_scrape": "2026-07-14T16:30:00"
  },
  "channels": [...]
}
```

---

## Configuration

### API Keys (`config.py`)

```python
API_KEY = "your_youtube_api_key_here"
GEMINI_API_KEY = "your_gemini_api_key_here"
MODEL = "gemini-3.1-flash-lite"
```

### Auto-Run Settings (`auto_config.py`)

```python
# Search configuration
KEYWORDS = ["keyword1", "keyword2"]
REGION_CODE = None  # or "US", "IN", etc.
SORT_ORDER = "viewCount"  # or "relevance", "date"
MAX_CHANNELS_PER_SEARCH = 10

# Re-scrape behavior
RESCRAPE_THRESHOLD_HOURS = 168  # 7 days

# Rate limiting
DELAY_BETWEEN_CHANNELS = 3  # seconds

# Analysis depth
DO_DEEP_ANALYSIS = False
DEEP_ANALYSIS_LIMIT = 2
DO_BENCHMARKING = False
```

---

## Database Schema

**Storage**: SQLite (`scraper.db`)  
**Approach**: Fully normalized, historical tracking

### Core Tables

```
scrape_runs
  ├── channels (one row per channel per scrape)
  │     ├── videos
  │     │     └── video_deep_analysis
  │     │           ├── video_transcript_topics
  │     │           ├── video_sentiment_themes
  │     │           └── video_thumbnail_elements
  │     ├── channel_content_styles
  │     ├── channel_brands
  │     ├── channel_audience_age_groups
  │     └── benchmarks
  └── (timestamps, search query, region)
```

### Key Features

- **Historical Tracking**: Every scrape creates NEW rows (not updates)
- **Normalized Lists**: All arrays stored in child tables
- **Growth Analysis**: Query same channel_id across time

### Example Queries

```sql
-- Track channel growth over time
SELECT scraped_at, subscriber_count, total_views
FROM channels
WHERE channel_id = 'UC...'
ORDER BY scraped_at DESC;

-- Find most active channels
SELECT channel_name, act_status, act_score
FROM channels
ORDER BY act_score DESC
LIMIT 10;

-- Recent scrapes
SELECT channel_name, scraped_at
FROM channels
WHERE scraped_at > datetime('now', '-7 days');
```

---

## Architecture

### Directory Structure

```
d:\Projects\Youtube-Lead-Generator\
├── web.py                     # Top-Level Web Server Launcher
├── main.py                    # Top-Level Scraper CLI Launcher
├── auto_run.py                # Top-Level Scraper Daemon Launcher
├── requirements.txt           # Python dependencies
│
├── src/                       # Enterprise Package Source Root (PyPA Standard)
│   └── youtube_lead_generator/
│       ├── core/              # Core infrastructure & workspace management
│       │   ├── config.py
│       │   ├── auto_config.py
│       │   ├── database.py
│       │   ├── workspace_manager.py
│       │   └── youtube_client.py
│       │
│       ├── services/          # Layered business extraction services
│       │   ├── youtube/       # Channel, Video, Comments API fetchers
│       │   ├── extractors/    # Category, Socials, Transcripts, Thumbnails
│       │   ├── analytics/     # Activity status & performance telemetry
│       │   └── system/        # Auth, Audit Logger, Job Queue
│       │
│       ├── ai/                # AI telemetry subsystem (Gemini 2.0)
│       │   ├── analyzers/
│       │   ├── builders/
│       │   ├── clients/
│       │   ├── prompts/
│       │   └── schemas/
│       │
│       └── web/               # Web application presentation layer
│           ├── app.py         # Flask app controllers & routes
│           └── templates/     # Jinja2 HTML templates
│
└── cli/                       # Command-line interface modules
    ├── main.py
    └── auto_run.py
    │   └── benchmarker.py
    ├── builders/
    │   └── creator_context_builder.py
    ├── schemas/               # Pydantic models
    └── prompts/               # XML prompts
```

### Data Flow

```
YouTube API → Services → Raw Data
                ↓
        Context Builder
                ↓
        AI Analyzers (Gemini)
                ↓
        Pydantic Validation
                ↓
        Database (SQLite)
                ↓
        Web Viewer (Flask)
```

### AI Integration

**Client**: Google Gemini API  
**Approach**: Structured output with Pydantic schemas  
**Prompts**: XML-formatted with role/task/rules pattern

**Example Analyzer**:
```python
class CreatorProfileAnalyzer(BaseAIService):
    def analyze(self, channel, videos, category, socials):
        context = {"channel": channel, "videos": videos, ...}
        return self.call_gemini(
            prompt_file="creator_profile.txt",
            context=context,
            response_schema=CreatorProfileSchema
        )
```

---

## API Reference

### Database Functions (`database.py`)

```python
# Check if channel needs re-scraping
should_rescrape(channel_id: str, threshold_hours: int) -> bool

# Get last scrape timestamp
get_last_scrape_time(channel_id: str) -> str | None

# Insert scrape run
insert_scrape_run(search_query, region_code, sort_order) -> int

# Insert channel data
insert_channel(run_id, channel, category, profile, ...) -> int

# Insert videos
insert_videos(channel_row_id, videos) -> dict

# Insert deep analysis
insert_video_deep_analysis(video_row_id, transcript, sentiment, thumbnail)
```

### Service Classes

```python
# Channel Service
ChannelService().get_channel(handle) -> dict
ChannelService().search_channels(keyword, order, max_results, region) -> list

# Video Service
VideoService().get_uploads(playlist_id, max_results) -> list

# Statistics Service
VideoStatisticsService().get_video_statistics(video_ids) -> list

# Activity Service
ActivityStatus.analyze(videos) -> dict
```

---

## Troubleshooting

### API Quota Issues

**Symptoms**: "quotaExceeded" errors, failed requests

**Solutions**:
1. Increase `DELAY_BETWEEN_CHANNELS` in auto_config.py
2. Reduce `MAX_CHANNELS_PER_SEARCH`
3. Disable `DO_DEEP_ANALYSIS`
4. Use higher `RESCRAPE_THRESHOLD_HOURS`
5. Wait 24 hours for quota reset

**Quota Usage**:
- Basic scrape: ~50 units
- Deep analysis per video: ~10 units
- Daily limit: 10,000 units
- Estimated: ~200 basic scrapes/day

### Database Errors

**"Database is locked"**:
- Close all other programs accessing scraper.db
- SQLite allows only one writer at a time

**"No such column"**:
- Database schema mismatch
- Run `python check_columns.py` to verify schema
- May need to delete scraper.db and re-scrape

### Web Viewer Issues

**"Address already in use"**:
- Port 5000 is taken
- Change port in simple_viewer.py: `app.run(port=8080)`

**"No data showing"**:
- Ensure scraper.db exists
- Run main.py or auto_run.py first to populate database
- Check terminal for errors

**"500 Internal Server Error"**:
- Check terminal for Python traceback
- Usually a column name mismatch
- Use simple_viewer.py instead of web_viewer.py

### Scraping Errors

**"Channel not found"**:
- Handle may be wrong (try with/without @)
- Channel may be deleted or private
- YouTube API may be rate limiting

**"Transcript unavailable"**:
- Not all videos have captions
- Auto-generated captions may be disabled
- This is normal - script will skip and continue

**"Thumbnail download failed"**:
- Video may not have high-res thumbnail
- Network timeout
- Script will skip and continue

---

## API Rate Limiting Best Practices

### YouTube API
- Daily quota: 10,000 units
- Channel details: ~1 unit
- Video details: ~1 unit per video
- Search: ~100 units per request

**Tips**:
- Use `DELAY_BETWEEN_CHANNELS` to pace requests
- Set `MAX_CHANNELS_PER_SEARCH` conservatively
- Avoid re-scraping too frequently (use `RESCRAPE_THRESHOLD_HOURS`)

### Gemini API
- Free tier: 60 requests/minute
- Paid tier: Higher limits

**Tips**:
- Disable `DO_DEEP_ANALYSIS` for bulk scraping
- Deep analysis calls Gemini 3x more per channel

---

## Advanced Usage

### Custom Analysis

Add your own analyzer in `ai/analyzers/`:

```python
from ai.base_ai_service import BaseAIService
from ai.schemas.my_schema import MySchema

class MyAnalyzer(BaseAIService):
    def analyze(self, channel, videos):
        context = {"channel": channel, "videos": videos}
        return self.call_gemini(
            prompt_file="my_prompt.txt",
            context=context,
            response_schema=MySchema
        )
```

### Export Data

```python
import sqlite3
import csv

conn = sqlite3.connect('scraper.db')
conn.row_factory = sqlite3.Row

channels = conn.execute("""
    SELECT channel_name, subscriber_count, total_views, act_status
    FROM channels
    ORDER BY subscriber_count DESC
""").fetchall()

with open('export.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Channel', 'Subscribers', 'Views', 'Status'])
    for ch in channels:
        writer.writerow([ch['channel_name'], ch['subscriber_count'], 
                        ch['total_views'], ch['act_status']])
```

### Historical Growth Analysis

```python
import sqlite3
import matplotlib.pyplot as plt

conn = sqlite3.connect('scraper.db')

data = conn.execute("""
    SELECT scraped_at, subscriber_count
    FROM channels
    WHERE channel_id = 'YOUR_CHANNEL_ID'
    ORDER BY scraped_at
""").fetchall()

dates = [row[0] for row in data]
subs = [row[1] for row in data]

plt.plot(dates, subs)
plt.title('Subscriber Growth')
plt.xticks(rotation=45)
plt.show()
```

---

## Security & Privacy

⚠️ **Important Notices**:

1. **API Keys**: Store securely, never commit to version control
2. **Local Use Only**: Web viewer has no authentication
3. **Data Privacy**: YouTube data subject to their Terms of Service
4. **Network Access**: Web viewer binds to 0.0.0.0 (accessible on LAN)

### For Production Use:
- Add authentication (Flask-Login, OAuth)
- Use HTTPS (nginx reverse proxy)
- Implement rate limiting
- Use production WSGI server (Gunicorn)
- Validate all user inputs
- Set restrictive CORS policies

---

## Comparison: Manual vs Auto vs Web

| Feature | Manual (`main.py`) | Auto (`auto_run.py`) | Web (`simple_viewer.py`) |
|---------|-------------------|---------------------|------------------------|
| **Mode** | Interactive | Automated | Read-only viewer |
| **Duration** | Single run | Continuous | On-demand |
| **Channel selection** | User chooses | All matching keywords | N/A (view only) |
| **Deep analysis** | Optional | Optional | N/A |
| **Benchmarking** | Yes | No | N/A |
| **Re-scrape control** | Manual | Time-based automatic | N/A |
| **Best for** | Deep-dive analysis | Market monitoring | Data exploration |
| **API usage** | Low (single channel) | High (continuous) | None |

---

## Contributing

To extend this project:

1. **Add new analyzers**: Create in `ai/analyzers/`
2. **New data sources**: Add services in `services/`
3. **Custom prompts**: Add XML files in `ai/prompts/`
4. **Database queries**: Extend `database.py`
5. **Web features**: Enhance `simple_viewer.py`

---

## License

This project is for educational and research purposes. Ensure compliance with YouTube's Terms of Service and API usage policies.

---

## Support

For issues or questions:
1. Check this README thoroughly
2. Review `AGENTS.md` for architecture details
3. Launch `python web.py` to inspect workspaces and database schemas via the Web Console
4. Check terminal output for error tracebacks

---

**Version**: 1.0  
**Last Updated**: July 2026  
**Python**: 3.8+  
**Dependencies**: See `requirements.txt`

---

## Quick Command Reference

```bash
# Web Console Interface (Primary)
python web.py

# Manual CLI channel discovery & analysis
python main.py

# Background continuous scraping daemon
python auto_run.py

# Install dependencies
pip install -r requirements.txt
```

---

**Happy Scraping! 🚀**
