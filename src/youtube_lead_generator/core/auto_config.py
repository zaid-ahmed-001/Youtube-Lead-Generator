"""
auto_config.py — Configuration for automatic keyword-based scraping

This file controls the behavior of auto-run mode in main.py.
"""

# ═══════════════════════════════════════════════════════════════════════════
# AUTO-RUN SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# Keywords to search for (will be combined with spaces)
KEYWORDS = ["tech review", "programming tutorial", "gaming"]

# Region code (2-letter ISO code) or None for global
# Examples: "US", "IN", "GB", "CA", "AU", "DE", "FR", "JP", "BR", "MX"
REGION_CODE = "IN"

# Sort order: "relevance", "viewCount", or "date"
SORT_ORDER = "viewCount"

# Maximum number of channels to fetch per search
MAX_CHANNELS_PER_SEARCH = 10

# Delay between processing channels (in seconds) to avoid API rate limits
DELAY_BETWEEN_CHANNELS = 10

# ═══════════════════════════════════════════════════════════════════════════
# RE-SCRAPE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# Number of hours before re-scraping a channel
# If a channel was scraped within this time, it will be skipped
# Set to 0 to always rescrape, or a large number (e.g., 720 = 30 days) to rarely rescrape
RESCRAPE_THRESHOLD_HOURS = 168  # 7 days (1 week)

# ═══════════════════════════════════════════════════════════════════════════
# ANALYSIS SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

# Enable/disable deep content analysis (transcripts, comments, thumbnails)
DO_DEEP_ANALYSIS = False

# Number of top videos to deeply analyze (only if DO_DEEP_ANALYSIS is True)
DEEP_ANALYSIS_LIMIT = 2

# Enable/disable benchmarking (requires manual competitor selection per run)
DO_BENCHMARKING = False
