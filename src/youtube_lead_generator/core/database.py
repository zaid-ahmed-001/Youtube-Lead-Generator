"""
database.py — SQLite persistence layer for the YouTube scraper.

Schema overview
───────────────
scrape_runs          one row per run (timestamp, query used)
  └─ channels        one row per channel per run (channel info + all scalar AI outputs)
       ├─ videos     one row per video belonging to that channel/run
       │    └─ video_deep_analysis          transcript/sentiment/thumbnail scalars
       │         ├─ video_transcript_topics
       │         ├─ video_transcript_ctas
       │         ├─ video_sentiment_themes
       │         ├─ video_sentiment_questions
       │         └─ video_thumbnail_elements
       ├─ channel_content_styles
       ├─ channel_brands / _games / _software / _hardware / _technologies / _creators
       ├─ channel_sponsor_brands / channel_sponsorship_types
       ├─ channel_audience_age_groups / _regions / _languages / _personas
       ├─ channel_audience_interests / _motivations / _purchase_categories / _evidence
       └─ benchmarks
            └─ benchmark_content_gaps

Every re-scrape of the same channel inserts a NEW row (full history kept).
All list/array fields are stored in separate child tables (fully normalized).
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from youtube_lead_generator.core.workspace_manager import WorkspaceManager


# ─────────────────────────────────────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    db_path = WorkspaceManager.get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Schema initialisation  (called once on import)
# ─────────────────────────────────────────────────────────────────────────────

_DDL = """
-- ── top-level run ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scrape_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_at    TEXT    NOT NULL,          -- ISO-8601 UTC
    search_query  TEXT,                      -- combined keyword query (NULL for handle mode)
    region_code   TEXT,
    sort_order    TEXT
);

-- ── channel (one row per channel per run) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS channels (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                  INTEGER NOT NULL REFERENCES scrape_runs(id),
    scraped_at              TEXT    NOT NULL,

    -- raw channel fields
    channel_id              TEXT    NOT NULL,
    channel_name            TEXT,
    description             TEXT,
    joined_date             TEXT,
    country                 TEXT,
    subscriber_count        INTEGER,
    total_views             INTEGER,
    total_videos            INTEGER,
    email                   TEXT,
    is_live_streamer        INTEGER DEFAULT 0,

    -- category
    primary_category        TEXT,

    -- creator profile (scalar fields)
    cp_primary_niche        TEXT,
    cp_secondary_niche      TEXT,
    cp_industry             TEXT,
    cp_target_audience      TEXT,
    cp_experience_level     TEXT,
    cp_primary_language     TEXT,
    cp_family_friendly      INTEGER,        -- 0/1
    cp_brand_friendly       INTEGER,
    cp_confidence           INTEGER,

    -- quality
    q_professionalism       INTEGER,
    q_production_quality    INTEGER,
    q_branding              INTEGER,
    q_consistency           INTEGER,
    q_originality           INTEGER,
    q_family_friendly       INTEGER,
    q_advertiser_friendly   INTEGER,
    q_confidence            INTEGER,

    -- sponsorship (scalar fields)
    sp_has_sponsorships     INTEGER,
    sp_affiliate_links      INTEGER,
    sp_business_email       INTEGER,
    sp_readiness            INTEGER,
    sp_confidence           INTEGER,

    -- audience (scalar fields)
    aud_gender_split        TEXT,
    aud_buying_intent       TEXT,
    aud_audience_type       TEXT,
    aud_skill_level         TEXT,
    aud_spending_power      TEXT,
    aud_community_strength  TEXT,
    aud_confidence          INTEGER,

    -- brands (scalar)
    br_confidence           INTEGER,

    -- activity
    act_status              TEXT,
    act_score               INTEGER,
    act_consistency_score   INTEGER,
    act_revived             INTEGER,
    act_last_upload_days    INTEGER,
    act_uploads_30d         INTEGER,
    act_uploads_90d         INTEGER,
    act_uploads_1y          INTEGER,
    act_avg_duration_min    REAL,
    act_expected_gap_days   INTEGER,
    act_actual_gap_days     REAL,
    act_upload_frequency    TEXT,
    act_frequency_ratio     REAL
);

-- ── channel list tables ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS channel_content_styles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_brands (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_games (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_software (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_hardware (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_technologies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_creators (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_sponsor_brands (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_sponsorship_types (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_age_groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_regions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_languages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_personas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_interests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_motivations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_purchase_categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_audience_evidence (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    value      TEXT NOT NULL
);

-- ── videos ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS videos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id       INTEGER NOT NULL REFERENCES channels(id),
    video_id         TEXT    NOT NULL,
    title            TEXT,
    published_at     TEXT,
    duration         TEXT,
    duration_seconds INTEGER,
    duration_minutes REAL,
    is_short         INTEGER,
    views            INTEGER,
    likes            INTEGER,
    comments         INTEGER,
    category_id      TEXT
);

-- ── video deep analysis (scalars) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS video_deep_analysis (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id             INTEGER NOT NULL REFERENCES videos(id),

    -- transcript
    tr_has_sponsor_pitch INTEGER,
    tr_sponsor_style     TEXT,

    -- sentiment
    s_overall_sentiment  TEXT,
    s_negativity_score   INTEGER,

    -- thumbnail
    th_clickbait_score   INTEGER,
    th_text_heavy        INTEGER,
    th_faces_present     INTEGER,
    th_vibe              TEXT
);

-- ── video deep analysis list tables ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS video_transcript_topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    deep_analysis_id INTEGER NOT NULL REFERENCES video_deep_analysis(id),
    value           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS video_transcript_ctas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    deep_analysis_id INTEGER NOT NULL REFERENCES video_deep_analysis(id),
    value           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS video_sentiment_themes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    deep_analysis_id INTEGER NOT NULL REFERENCES video_deep_analysis(id),
    value           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS video_sentiment_questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    deep_analysis_id INTEGER NOT NULL REFERENCES video_deep_analysis(id),
    value           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS video_thumbnail_elements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    deep_analysis_id INTEGER NOT NULL REFERENCES video_deep_analysis(id),
    value           TEXT NOT NULL
);

-- ── benchmarks ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS benchmarks (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               INTEGER NOT NULL REFERENCES scrape_runs(id),
    channel_a_id         INTEGER NOT NULL REFERENCES channels(id),
    channel_b_handle     TEXT    NOT NULL,
    scraped_at           TEXT    NOT NULL,

    winner               TEXT,
    engagement_comparison    TEXT,
    audience_differences     TEXT,
    quality_differences      TEXT,
    activity_comparison      TEXT,
    growth_prediction        TEXT
);
CREATE TABLE IF NOT EXISTS benchmark_content_gaps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_id INTEGER NOT NULL REFERENCES benchmarks(id),
    value        TEXT    NOT NULL
);
"""


def init_db():
    """Create all tables if they don't exist yet and run migrations."""
    with get_connection() as conn:
        conn.executescript(_DDL)
        try:
            cursor = conn.execute("PRAGMA table_info(channels)")
            cols = [r[1] for r in cursor.fetchall()]
            if "is_live_streamer" not in cols:
                conn.execute("ALTER TABLE channels ADD COLUMN is_live_streamer INTEGER DEFAULT 0")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _insert_list(conn, table: str, parent_col: str, parent_id: int, values: list):
    """Bulk-insert rows into a list/child table."""
    if not values:
        return
    conn.executemany(
        f"INSERT INTO {table} ({parent_col}, value) VALUES (?, ?)",
        [(parent_id, v) for v in values if v]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public insert functions
# ─────────────────────────────────────────────────────────────────────────────

def insert_scrape_run(search_query: str = None, region_code: str = None, sort_order: str = None) -> int:
    """Create a new scrape_run record and return its id."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO scrape_runs (scraped_at, search_query, region_code, sort_order) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), search_query, region_code, sort_order)
        )
        return cur.lastrowid


def insert_channel(
    run_id: int,
    channel: dict,
    category: dict,
    profile,
    quality,
    sponsorship,
    audience,
    brands,
    activity: dict,
    is_live_streamer: int = 0,
) -> int:
    """
    Insert a full channel snapshot and all its normalized list children.
    Returns the new channels.id.
    """
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:

        # ── main channel row ────────────────────────────────────────────────
        cur = conn.execute("""
            INSERT INTO channels (
                run_id, scraped_at,
                channel_id, channel_name, description, joined_date, country,
                subscriber_count, total_views, total_videos, email, is_live_streamer,
                primary_category,
                cp_primary_niche, cp_secondary_niche, cp_industry,
                cp_target_audience, cp_experience_level, cp_primary_language,
                cp_family_friendly, cp_brand_friendly, cp_confidence,
                q_professionalism, q_production_quality, q_branding,
                q_consistency, q_originality, q_family_friendly,
                q_advertiser_friendly, q_confidence,
                sp_has_sponsorships, sp_affiliate_links, sp_business_email,
                sp_readiness, sp_confidence,
                aud_gender_split, aud_buying_intent, aud_audience_type,
                aud_skill_level, aud_spending_power, aud_community_strength,
                aud_confidence,
                br_confidence,
                act_status, act_score, act_consistency_score, act_revived,
                act_last_upload_days, act_uploads_30d, act_uploads_90d,
                act_uploads_1y, act_avg_duration_min, act_expected_gap_days,
                act_actual_gap_days, act_upload_frequency, act_frequency_ratio
            ) VALUES (
                ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?,
                ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?
            )
        """, (
            run_id, now,
            channel["channel_id"], channel["channel_name"],
            channel.get("description"), channel.get("joined_date"),
            channel.get("country"), channel.get("subscriber_count"),
            channel.get("total_views"), channel.get("total_videos"),
            channel.get("email"), int(is_live_streamer),
            category.get("primary_category") if category else None,
            # creator profile
            getattr(profile, "primary_niche", None),
            getattr(profile, "secondary_niche", None),
            getattr(profile, "industry", None),
            getattr(profile, "target_audience", None),
            getattr(profile, "experience_level", None),
            getattr(profile, "primary_language", None),
            int(getattr(profile, "family_friendly", False)),
            int(getattr(profile, "brand_friendly", False)),
            getattr(profile, "confidence", None),
            # quality
            getattr(quality, "professionalism", None),
            getattr(quality, "production_quality", None),
            getattr(quality, "branding", None),
            getattr(quality, "consistency", None),
            getattr(quality, "originality", None),
            int(getattr(quality, "family_friendly", False)),
            int(getattr(quality, "advertiser_friendly", False)),
            getattr(quality, "confidence", None),
            # sponsorship
            int(getattr(sponsorship, "has_sponsorships", False)),
            int(getattr(sponsorship, "affiliate_links", False)),
            int(getattr(sponsorship, "business_email_present", False)),
            getattr(sponsorship, "sponsorship_readiness", None),
            getattr(sponsorship, "confidence", None),
            # audience scalars
            getattr(audience, "gender_split", None),
            getattr(audience, "buying_intent", None),
            getattr(audience, "audience_type", None),
            getattr(audience, "skill_level", None),
            getattr(audience, "spending_power", None),
            getattr(audience, "community_strength", None),
            getattr(audience, "confidence", None),
            # brands scalar
            getattr(brands, "confidence", None),
            # activity
            activity.get("status"),
            activity.get("activity_score"),
            activity.get("consistency_score"),
            int(activity.get("revived", False)),
            activity.get("last_upload_days"),
            activity.get("uploads_last_30_days"),
            activity.get("uploads_last_90_days"),
            activity.get("uploads_last_year"),
            activity.get("average_video_duration_minutes"),
            activity.get("expected_upload_gap_days"),
            activity.get("actual_upload_gap_days"),
            activity.get("upload_frequency"),
            activity.get("frequency_ratio"),
        ))

        ch_row_id = cur.lastrowid

        # ── channel list children ───────────────────────────────────────────
        _insert_list(conn, "channel_content_styles",   "channel_id", ch_row_id, getattr(profile,      "content_styles",    []))
        _insert_list(conn, "channel_brands",           "channel_id", ch_row_id, getattr(brands,       "brands",            []))
        _insert_list(conn, "channel_games",            "channel_id", ch_row_id, getattr(brands,       "games",             []))
        _insert_list(conn, "channel_software",         "channel_id", ch_row_id, getattr(brands,       "software",          []))
        _insert_list(conn, "channel_hardware",         "channel_id", ch_row_id, getattr(brands,       "hardware",          []))
        _insert_list(conn, "channel_technologies",     "channel_id", ch_row_id, getattr(brands,       "technologies",      []))
        _insert_list(conn, "channel_creators",         "channel_id", ch_row_id, getattr(brands,       "creators",          []))
        _insert_list(conn, "channel_sponsor_brands",   "channel_id", ch_row_id, getattr(sponsorship,  "brands",            []))
        _insert_list(conn, "channel_sponsorship_types","channel_id", ch_row_id, getattr(sponsorship,  "sponsorship_types", []))
        _insert_list(conn, "channel_audience_age_groups",         "channel_id", ch_row_id, getattr(audience, "age_groups",          []))
        _insert_list(conn, "channel_audience_regions",            "channel_id", ch_row_id, getattr(audience, "regions",             []))
        _insert_list(conn, "channel_audience_languages",          "channel_id", ch_row_id, getattr(audience, "languages",           []))
        _insert_list(conn, "channel_audience_personas",           "channel_id", ch_row_id, getattr(audience, "audience_personas",   []))
        _insert_list(conn, "channel_audience_interests",          "channel_id", ch_row_id, getattr(audience, "interests",           []))
        _insert_list(conn, "channel_audience_motivations",        "channel_id", ch_row_id, getattr(audience, "motivations",         []))
        _insert_list(conn, "channel_audience_purchase_categories","channel_id", ch_row_id, getattr(audience, "purchase_categories", []))
        _insert_list(conn, "channel_audience_evidence",           "channel_id", ch_row_id, getattr(audience, "evidence",            []))

        return ch_row_id


def insert_videos(channel_row_id: int, videos: list) -> dict:
    """
    Insert all videos for a channel. Returns a dict of {video_id_str: row_id}
    so callers can reference the right FK when inserting deep analysis.
    """
    id_map = {}
    with get_connection() as conn:
        for v in videos:
            cur = conn.execute("""
                INSERT INTO videos (
                    channel_id, video_id, title, published_at,
                    duration, duration_seconds, duration_minutes, is_short,
                    views, likes, comments, category_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                channel_row_id,
                v["video_id"], v["title"], v.get("published_at"),
                v.get("duration"), v.get("duration_seconds"),
                v.get("duration_minutes"), int(v.get("is_short", False)),
                v.get("views"), v.get("likes"), v.get("comments"),
                v.get("category_id"),
            ))
            id_map[v["video_id"]] = cur.lastrowid
    return id_map


def insert_video_deep_analysis(
    video_row_id: int,
    transcript_profile=None,
    sentiment_profile=None,
    thumbnail_profile=None,
):
    """Insert deep analysis results for a single video."""
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO video_deep_analysis (
                video_id,
                tr_has_sponsor_pitch, tr_sponsor_style,
                s_overall_sentiment, s_negativity_score,
                th_clickbait_score, th_text_heavy, th_faces_present, th_vibe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_row_id,
            int(getattr(transcript_profile, "has_sponsor_pitch", False)) if transcript_profile else None,
            getattr(transcript_profile, "sponsor_pitch_style", None)     if transcript_profile else None,
            getattr(sentiment_profile, "overall_sentiment", None)        if sentiment_profile else None,
            getattr(sentiment_profile, "negativity_score", None)         if sentiment_profile else None,
            getattr(thumbnail_profile, "clickbait_score", None)          if thumbnail_profile else None,
            int(getattr(thumbnail_profile, "text_heavy", False))         if thumbnail_profile else None,
            int(getattr(thumbnail_profile, "faces_present", False))      if thumbnail_profile else None,
            getattr(thumbnail_profile, "vibe", None)                     if thumbnail_profile else None,
        ))
        da_id = cur.lastrowid

        if transcript_profile:
            _insert_list(conn, "video_transcript_topics",    "deep_analysis_id", da_id, getattr(transcript_profile, "core_topics",        []))
            _insert_list(conn, "video_transcript_ctas",      "deep_analysis_id", da_id, getattr(transcript_profile, "call_to_actions",     []))
        if sentiment_profile:
            _insert_list(conn, "video_sentiment_themes",     "deep_analysis_id", da_id, getattr(sentiment_profile,  "common_themes",       []))
            _insert_list(conn, "video_sentiment_questions",  "deep_analysis_id", da_id, getattr(sentiment_profile,  "audience_questions",  []))
        if thumbnail_profile:
            _insert_list(conn, "video_thumbnail_elements",   "deep_analysis_id", da_id, getattr(thumbnail_profile,  "elements",            []))


def insert_benchmark(
    run_id: int,
    channel_a_row_id: int,
    competitor_handle: str,
    benchmark,
):
    """Insert a benchmark comparison result."""
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO benchmarks (
                run_id, channel_a_id, channel_b_handle, scraped_at,
                winner, engagement_comparison, audience_differences,
                quality_differences, activity_comparison, growth_prediction
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            channel_a_row_id,
            competitor_handle,
            datetime.now(timezone.utc).isoformat(),
            getattr(benchmark, "winner",               None),
            getattr(benchmark, "engagement_comparison", None),
            getattr(benchmark, "audience_differences",  None),
            getattr(benchmark, "quality_differences",   None),
            getattr(benchmark, "activity_comparison",   None),
            getattr(benchmark, "growth_prediction",     None),
        ))
        bm_id = cur.lastrowid
        _insert_list(conn, "benchmark_content_gaps", "benchmark_id", bm_id, getattr(benchmark, "content_gaps", []))


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers for auto-run mode
# ─────────────────────────────────────────────────────────────────────────────

def get_last_scrape_time(channel_id: str) -> str | None:
    """
    Returns the ISO timestamp of the most recent scrape for a given channel_id,
    or None if the channel has never been scraped.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT scraped_at FROM channels WHERE channel_id = ? ORDER BY scraped_at DESC LIMIT 1",
            (channel_id,)
        ).fetchone()
        return row["scraped_at"] if row else None


def should_rescrape(channel_id: str, threshold_hours: int) -> bool:
    """
    Returns True if the channel should be scraped:
    - Never scraped before, OR
    - Last scrape was more than threshold_hours ago
    """
    from datetime import datetime, timezone, timedelta
    
    last_scrape = get_last_scrape_time(channel_id)
    if not last_scrape:
        return True
    
    last_dt = datetime.fromisoformat(last_scrape)
    # If stored timestamp is timezone-naive, assume UTC
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    now_dt = datetime.now(timezone.utc)
    hours_since = (now_dt - last_dt).total_seconds() / 3600
    
    return hours_since >= threshold_hours


def delete_channels(channel_ids: list) -> int:
    """
    Deletes channels by primary key IDs or channel_ids, along with associated child table records.
    Returns the count of deleted channel rows.
    """
    if not channel_ids:
        return 0
    with get_connection() as conn:
        placeholders = ",".join(["?"] * len(channel_ids))
        rows = conn.execute(
            f"SELECT id, channel_id FROM channels WHERE id IN ({placeholders}) OR channel_id IN ({placeholders})",
            list(channel_ids) + list(channel_ids)
        ).fetchall()
        if not rows:
            return 0
        int_ids = [r["id"] for r in rows]
        ch_str_ids = [r["channel_id"] for r in rows if r["channel_id"]]
        
        id_placeholders = ",".join(["?"] * len(int_ids))

        tables_by_int_id = ["videos", "content_styles", "brands", "audience_demographics", "creator_profiles", "sponsorship_readiness", "quality_scores", "activity_metrics"]
        for tbl in tables_by_int_id:
            try:
                conn.execute(f"DELETE FROM {tbl} WHERE channel_id IN ({id_placeholders})", int_ids)
            except Exception:
                pass

        if ch_str_ids:
            ch_placeholders = ",".join(["?"] * len(ch_str_ids))
            for tbl in ["videos", "creator_profiles", "sponsorship_readiness", "quality_scores", "activity_metrics"]:
                try:
                    conn.execute(f"DELETE FROM {tbl} WHERE channel_id IN ({ch_placeholders})", ch_str_ids)
                except Exception:
                    pass

        cursor = conn.execute(f"DELETE FROM channels WHERE id IN ({id_placeholders})", int_ids)
        conn.commit()
        return cursor.rowcount


def clear_workspace() -> bool:
    """
    Clears all scraped records from the current active workspace database.
    """
    with get_connection() as conn:
        tables = ["channels", "videos", "scrape_runs", "content_styles", "brands", "audience_demographics", "creator_profiles", "sponsorship_readiness", "quality_scores", "activity_metrics", "benchmarks"]
        for tbl in tables:
            try:
                conn.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass
        conn.commit()
        return True


# ── auto-init on import ───────────────────────────────────────────────────────
init_db()