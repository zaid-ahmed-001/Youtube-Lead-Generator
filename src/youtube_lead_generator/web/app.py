"""
YouTube Scraper Web Console — Full-featured professional UI with Excel-like interface

Features:
1. Channel Data Browser (Excel-style grid)
2. Database Dictionary & Schema viewer
3. YouTube Scraper Operations
4. Database Management Tools
5. Configuration & Settings
6. Analytics & Reporting

Usage:
    python web.py
    Then open http://localhost:5000
"""

from flask import Flask, render_template, render_template_string, jsonify, request, session, Response
import sqlite3
from pathlib import Path
import os
import sys
import json
import time
import threading
from datetime import datetime
from functools import wraps
from youtube_lead_generator.services.system.auth_service import AuthService
from youtube_lead_generator.services.system.audit_logger import AuditLogger

from youtube_lead_generator.core.database import (
    insert_scrape_run, insert_channel, insert_videos, 
    insert_video_deep_analysis, insert_benchmark,
    should_rescrape, get_connection as get_scraper_db_connection
)
from youtube_lead_generator.services.youtube.channel_service import ChannelService
from youtube_lead_generator.services.youtube.video_service import VideoService
from youtube_lead_generator.services.youtube.video_statistics_service import VideoStatisticsService
from youtube_lead_generator.services.extractors.category_extractor import CategoryExtractor
from youtube_lead_generator.services.extractors.social_extractor import SocialExtractor
from youtube_lead_generator.services.extractors.transcript_extractor import TranscriptExtractor
from youtube_lead_generator.services.youtube.comment_service import CommentService
from youtube_lead_generator.services.extractors.thumbnail_extractor import ThumbnailExtractor
from youtube_lead_generator.services.analytics.activity_service import ActivityStatus

from youtube_lead_generator.ai.analyzers.creator_profile_analyzer import CreatorProfileAnalyzer
from youtube_lead_generator.ai.analyzers.audience_analyzer import AudienceAnalyzer
from youtube_lead_generator.ai.analyzers.brand_analyzer import BrandDetector
from youtube_lead_generator.ai.analyzers.quality_analyzer import QualityAnalyzer
from youtube_lead_generator.ai.analyzers.sponsorship_analyzer import SponsorshipAnalyzer
from youtube_lead_generator.ai.analyzers.sentiment_analyzer import SentimentAnalyzer
from youtube_lead_generator.ai.analyzers.transcript_analyzer import TranscriptAnalyzer
from youtube_lead_generator.ai.analyzers.thumbnail_analyzer import ThumbnailAnalyzer
from youtube_lead_generator.ai.analyzers.benchmark_analyzer import Benchmarker
from youtube_lead_generator.ai.builders.creator_context_builder import CreatorContextBuilder

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'youtube-scraper-web-console-secret-key-2026')
from youtube_lead_generator.core.workspace_manager import WorkspaceManager
from youtube_lead_generator.core.database import init_db

# Initialize services
channel_service = ChannelService()
video_service = VideoService()
stats_service = VideoStatisticsService()

# Country codes mapping
COUNTRY_CODES = {
    "india": "IN", "usa": "US", "us": "US", "uk": "GB", "united kingdom": "GB",
    "canada": "CA", "australia": "AU", "germany": "DE", "france": "FR",
    "japan": "JP", "brazil": "BR", "mexico": "MX"
}


# Background task management
import queue
import traceback
from collections import deque

background_tasks = {}
scrape_logs = deque(maxlen=200)
scrape_is_running = False
scrape_cancel_flag = False
scrape_lock = threading.Lock()

autorunner_active = False
autorunner_threshold = 24
autorunner_logs = deque(maxlen=200)
autorunner_thread = None


# ==========================================
# DATABASE HELPER & RESILIENCE LAYER
# ==========================================

def get_db_connection():
    """Establishes connection and configures Row factory."""
    db_path = WorkspaceManager.get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def table_exists(conn, table_name):
    """Verifies table existence within SQLite catalog."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def get_table_columns(conn, table_name):
    """Retrieves column catalog to enable defensive SQL schema building."""
    if not table_exists(conn, table_name):
        return []
    cursor = conn.cursor()
    # Validate table_name is alphanumeric/underscore to prevent SQL injection
    if not all(c.isalnum() or c == '_' for c in table_name):
        return []
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]

def init_mock_db():
    """
    Generates a realistic mock database if the active workspace database is empty.
    Ensures immediate out-of-the-box validation of the interface.
    """
    print("⚠️ Active workspace database not found or empty. Provisioning mock database...")
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create Core Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name TEXT NOT NULL,
            cp_primary_niche TEXT,
            subscriber_count INTEGER,
            total_views INTEGER,
            total_videos INTEGER,
            act_status TEXT,
            act_score INTEGER,
            q_production_quality INTEGER,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            title TEXT,
            views INTEGER,
            likes INTEGER,
            duration_minutes REAL,
            FOREIGN KEY(channel_id) REFERENCES channels(id)
        )
    """)
    
    # Mock Helper Tables
    cursor.execute("CREATE TABLE IF NOT EXISTS content_styles (channel_id INTEGER, style TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS brands (channel_id INTEGER, brand TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS audience_demographics (channel_id INTEGER, category TEXT, value TEXT)")

    # Insert Runs
    cursor.execute("INSERT INTO scrape_runs (scraped_at) VALUES ('2026-07-14 10:00:00')")
    cursor.execute("INSERT INTO scrape_runs (scraped_at) VALUES ('2026-07-14 12:00:00')")

    # Insert Channels
    mock_channels = [
        ("TechUnboxed", "Technology", 1450000, 122000000, 312, "Excellent", 92, 9, "2026-07-14 12:00:00"),
        ("Lo-Fi Study Beats", "Music", 3200000, 480000000, 84, "Healthy", 85, 8, "2026-07-14 12:01:00"),
        ("The Budget Kitchen", "Cooking", 450000, 24000000, 185, "Active", 72, 7, "2026-07-14 12:02:00"),
        ("Coffee & Code", "Education", 120000, 3100000, 42, "Healthy", 79, 8, "2026-07-14 12:03:00"),
        ("Retro Gamer Archive", "Gaming", 85000, 12000000, 950, "Dormant", 20, 5, "2026-07-14 12:04:00")
    ]
    
    for ch in mock_channels:
        cursor.execute("""
            INSERT INTO channels (channel_name, cp_primary_niche, subscriber_count, total_views, total_videos, act_status, act_score, q_production_quality, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ch)
        ch_id = cursor.lastrowid

        # Insert Child video records
        cursor.execute("INSERT INTO videos (channel_id, title, views, likes, duration_minutes) VALUES (?, ?, ?, ?, ?)",
                       (ch_id, f"The Ultimate {ch[0]} Guide", int(ch[3]*0.05), int(ch[3]*0.002), 12.5))
        cursor.execute("INSERT INTO videos (channel_id, title, views, likes, duration_minutes) VALUES (?, ?, ?, ?, ?)",
                       (ch_id, f"Why I changed my mind about {ch[1]}", int(ch[3]*0.02), int(ch[3]*0.001), 18.2))
        
        # Insert Meta associations
        cursor.execute("INSERT INTO content_styles (channel_id, style) VALUES (?, ?)", (ch_id, "Video Essay"))
        cursor.execute("INSERT INTO content_styles (channel_id, style) VALUES (?, ?)", (ch_id, "Highly Edited"))
        cursor.execute("INSERT INTO brands (channel_id, brand) VALUES (?, ?)", (ch_id, "SponsorBrand Inc."))
        cursor.execute("INSERT INTO audience_demographics (channel_id, category, value) VALUES (?, 'age', '18-24')", (ch_id,))
        cursor.execute("INSERT INTO audience_demographics (channel_id, category, value) VALUES (?, 'region', 'United States')", (ch_id,))

    conn.commit()
    conn.close()
    print("✓ Mock database provisioned successfully.")

# ==========================================
# ENTERPRISE SPREADSHEET FRONTEND TEMPLATE
# ==========================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Scraper Database Console</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f7f7f5;
    --text-main: #37352f;
    --text-secondary: rgba(55, 53, 47, 0.65);
    --border-color: #e9e9e7;
    --hover-bg: #efefed;
    --notion-dark: #2f2f2f;
    --notion-blue: #2383e2;
    --notion-blue-bg: #e6f3ff;
    --excel-blue: var(--notion-blue);
}

body {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-main);
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.ribbon-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 24px;
    background-color: var(--bg-primary);
    border-bottom: 1px solid var(--border-color);
}
.ribbon-brand {
    display: flex;
    align-items: center;
    gap: 12px;
}
.ribbon-brand h1 {
    font-size: 16px;
    font-weight: 600;
    margin: 0;
}
.header-divider {
    width: 1px;
    height: 20px;
    background-color: var(--border-color);
    margin: 0 12px;
}

svg, svg.excel-icon, svg.workspace-icon, svg.ws-item-check {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    fill: currentColor;
}
svg.ribbon-logo {
    width: 24px;
    height: 24px;
}
svg.status-icon {
    width: 14px;
    height: 14px;
}

.sheet-tabs {
    display: flex;
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-secondary);
    padding: 0 12px;
}
.sheet-tab {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    font-size: 14px;
    color: var(--text-secondary);
}
.sheet-tab.active {
    color: var(--text-main);
    border-bottom-color: var(--text-main);
    font-weight: 500;
}
.sheet-tab:hover:not(.active) {
    background: var(--hover-bg);
}

.workbook-container {
    flex: 1;
    overflow: auto;
    background: var(--bg-primary);
}
.sheet-content {
    display: none;
    padding: 24px;
}
.sheet-content.active {
    display: block;
}

.summary-dashboard {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
}
.kpi-tile {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 16px;
    flex: 1;
    display: flex;
    flex-direction: column;
    box-shadow: rgba(15, 15, 15, 0.05) 0px 1px 2px;
}
.kpi-label {
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 24px;
    font-weight: 600;
}

.table-wrapper {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    overflow-x: auto;
}
.excel-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}
.excel-table th, .excel-table td {
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}
.excel-table th {
    background: var(--bg-secondary);
    font-weight: 500;
    color: var(--text-secondary);
    white-space: nowrap;
}
.excel-table tr:hover td {
    background: var(--bg-secondary);
}

button {
    cursor: pointer;
    font-family: inherit;
}
.excel-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-main);
    font-size: 14px;
    transition: background 0.1s;
}
.excel-btn:hover {
    background: var(--hover-bg);
}
.excel-btn-primary {
    background: var(--notion-blue);
    color: white;
    border-color: var(--notion-blue);
}
.excel-btn-primary:hover {
    background: #1a6fb0;
}

.modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(15, 15, 15, 0.6);
    z-index: 1000;
    align-items: center;
    justify-content: center;
}
.inspector-modal, .ops-modal {
    background: var(--bg-primary);
    border-radius: 8px;
    width: 90%;
    max-width: 800px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: rgba(15, 15, 15, 0.1) 0px 5px 15px;
}
.inspector-header, .ops-modal-header {
    padding: 16px 24px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.inspector-header h2, .ops-modal-header h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
}
.inspector-body, .ops-modal-body {
    padding: 24px;
    overflow-y: auto;
}
.close-btn {
    background: none;
    border: none;
    font-size: 24px;
    line-height: 1;
    color: var(--text-secondary);
}
.close-btn:hover {
    color: var(--text-main);
}

.workspace-picker-wrapper {
    position: relative;
}
.workspace-picker-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border-radius: 4px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    font-size: 13px;
}
.workspace-picker-btn:hover {
    background: var(--hover-bg);
}
.workspace-dropdown-menu {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 4px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    box-shadow: rgba(15, 15, 15, 0.1) 0px 5px 10px;
    min-width: 200px;
    z-index: 100;
}
.workspace-dropdown-menu.show {
    display: block;
}
.ws-dropdown-item, .ws-dropdown-action {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    cursor: pointer;
    border: none;
    background: none;
    width: 100%;
    text-align: left;
    font-size: 14px;
    color: var(--text-main);
}
.ws-dropdown-item:hover, .ws-dropdown-action:hover {
    background: var(--hover-bg);
}
.ws-item-check {
    opacity: 0;
}
.ws-dropdown-item.active .ws-item-check {
    opacity: 1;
}

.tag-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    font-size: 12px;
    margin: 2px;
}
.toolbar-controls {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
    align-items: center;
}
.excel-input, .excel-select {
    padding: 6px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-main);
    font-size: 14px;
    font-family: inherit;
}
.excel-input:focus, .excel-select:focus {
    outline: none;
    border-color: var(--notion-blue);
    box-shadow: 0 0 0 1px var(--notion-blue);
}

.terminal-console {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: monospace;
    padding: 10px;
    border-radius: 4px;
    height: 300px;
    overflow-y: auto;
}
</style>

</head>
<body>

    <header class="ribbon-bar">
        <div class="ribbon-brand">
            <svg class="ribbon-logo" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 4.02 2 6.5s4.48 4.5 10 4.5 10-2.02 10-4.5S17.52 2 12 2zm0 13c-4.43 0-8-1.57-8-3.5v3c0 1.93 3.57 3.5 8 3.5s8-1.57 8-3.5v-3c0 1.93-3.57 3.5-8 3.5zm0-6.5c-4.43 0-8-1.57-8-3.5v3c0 1.93 3.57 3.5 8 3.5s8-1.57 8-3.5v-3c0 1.93-3.57 3.5-8 3.5z"/>
            </svg>
            <h1>YouTube Scraper Console</h1>
            <div class="header-divider"></div>
            <div class="workspace-picker-wrapper" title="Switch Active Scraper Workspace">
                <button class="workspace-picker-btn" id="workspacePickerBtn" onclick="toggleWorkspaceDropdown(event)">
                    <svg class="workspace-icon" viewBox="0 0 24 24">
                        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14zM7 10h2v7H7zm4-3h2v10h-2zm4 6h2v4h-2z"/>
                    </svg>
                    <span class="workspace-label">Workspace:</span>
                    <span id="currentWorkspaceText" class="workspace-active-name">default</span>
                    <svg class="workspace-chevron" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
                </button>

                <!-- Custom Floating Workspace Popover -->
                <div id="workspaceDropdownMenu" class="workspace-dropdown-menu">
                    <div class="ws-dropdown-header">Active Workspace</div>
                    <div class="ws-dropdown-list" id="workspaceList">
                        <div class="ws-dropdown-item active" onclick="selectWorkspace('default')">
                            <svg class="ws-item-check" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                            <span class="ws-item-name">default</span>
                        </div>
                    </div>
                    <div class="ws-dropdown-divider"></div>
                    <button class="ws-dropdown-action" onclick="createWorkspacePrompt()">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
                        <span>+ Create New Workspace...</span>
                    </button>
                </div>
            </div>
        </div>
        <div class="ribbon-actions" style="display: flex; align-items: center; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.2); padding: 4px 10px; border-radius: 12px; font-size: 11px;">
                <svg class="excel-icon" viewBox="0 0 24 24" style="fill: white; width: 14px; height: 14px;"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                <span id="currentUserLabel" style="font-weight: 700;">Admin: System Administrator</span>
            </div>
        </div>
    </header>

    <nav class="sheet-tabs">
        <button class="sheet-tab active" onclick="switchSheet('grid-sheet', this)">
            <svg class="excel-icon" viewBox="0 0 24 24" style="fill: var(--excel-blue)">
                <path d="M4 18h17v-6H4v6zM4 5v6h17V5H4z"/>
            </svg>
            Channel Registry Grid
        </button>
        <button class="sheet-tab" onclick="switchSheet('scraper-sheet', this)">
            <svg class="excel-icon" viewBox="0 0 24 24" style="fill: var(--text-secondary)">
                <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 14z"/>
            </svg>
            Scraper Operations
        </button>
        <button class="sheet-tab" onclick="switchSheet('analytics-sheet', this); loadAnalyticsData();">
            <svg class="excel-icon" viewBox="0 0 24 24" style="fill: var(--text-secondary)">
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/>
            </svg>
            Visual Analytics BI
        </button>
    </nav>

    <main class="workbook-container">

        <section id="grid-sheet" class="sheet-content active">
            <div class="summary-dashboard" id="stats">
                <div class="kpi-tile">
                    <span class="kpi-label">Total Channels</span>
                    <span class="kpi-value" id="totalChannels">-</span>
                </div>
                <div class="kpi-tile">
                    <span class="kpi-label">Scrape Runs</span>
                    <span class="kpi-value" id="totalRuns">-</span>
                </div>
                <div class="kpi-tile">
                    <span class="kpi-label">Total Video Records</span>
                    <span class="kpi-value" id="totalVideos">-</span>
                </div>
                <div class="kpi-tile">
                    <span class="kpi-label">Latest Scrape Cycle</span>
                    <span class="kpi-value" id="latestScrape">-</span>
                </div>
            </div>

            <div class="formula-bar-container">
                <div class="formula-fx-label">fx</div>
                <div class="formula-divider"></div>
                <div class="formula-input-wrapper">
                    <svg class="formula-search-icon" viewBox="0 0 24 24">
                        <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
                    </svg>
                    <input type="text" id="searchInput" class="formula-input" placeholder="Enter search criteria (e.g. channel name, niche metadata, topics)...">
                </div>
            </div>

            <!-- Line 1: Sorting & View Controls -->
            <div class="data-filter-row">
                <div class="filter-group">
                    <span class="filter-label">Sort Column:</span>
                    <select id="sortBy" class="excel-dropdown" onchange="loadChannels(1)">
                        <option value="scraped_at">scraped_at (Latest)</option>
                        <option value="subscriber_count">subscriber_count (Subscribers)</option>
                        <option value="total_views">total_views (Total Views)</option>
                        <option value="total_videos">total_videos (Total Videos)</option>
                        <option value="channel_name">channel_name (Name A-Z)</option>
                        <option value="act_score">act_score (Activity Score)</option>
                        <option value="act_last_upload_days">act_last_upload_days (Last Upload)</option>
                        <option value="q_production_quality">q_production_quality (Quality)</option>
                        <option value="sp_readiness">sp_readiness (Sponsorship Readiness)</option>
                        <option value="cp_primary_niche">cp_primary_niche (Niche)</option>
                        <option value="id">id (Database ID)</option>
                    </select>
                </div>

                <div class="filter-group">
                    <span class="filter-label">Order:</span>
                    <select id="sortOrder" class="excel-dropdown" style="min-width: 110px;" onchange="loadChannels(1)">
                        <option value="DESC">Descending</option>
                        <option value="ASC">Ascending</option>
                    </select>
                </div>
                
                <div class="filter-group">
                    <span class="filter-label">Limit Rows:</span>
                    <select id="perPage" class="excel-dropdown" style="min-width: 90px;" onchange="loadChannels(1)">
                        <option value="10">10 rows</option>
                        <option value="25">25 rows</option>
                        <option value="50" selected>50 rows</option>
                        <option value="100">100 rows</option>
                        <option value="250">250 rows</option>
                    </select>
                </div>

                <div class="filter-group">
                    <button class="excel-btn" onclick="resetFilters()" title="Reset all sorting and filters to default">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                        Reset Filters
                    </button>
                </div>

                <!-- Column Picker Filter -->
                <div class="filter-group" style="position: relative;">
                    <button class="excel-btn" id="colPickerBtn" onclick="toggleColumnPicker(event)">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
                        <span id="colPickerLabel">Columns (57/57)</span>
                        <svg class="excel-icon" viewBox="0 0 24 24" style="width: 10px; height: 10px;"><path d="M7 10l5 5 5-5z"/></svg>
                    </button>
                    
                    <div id="columnPickerMenu" class="column-picker-menu">
                        <div class="col-picker-header">
                            <span>Select Visible Columns</span>
                            <button class="col-picker-close" onclick="toggleColumnPicker(event)" title="Close">
                                <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                            </button>
                        </div>
                        <div class="col-picker-search">
                            <input type="text" id="colSearchInput" placeholder="Search columns..." onkeyup="filterPickerColumns()" class="win-input-field" style="margin: 0; padding: 4px 8px; font-size: 11px;">
                        </div>
                        <div class="col-picker-actions">
                            <button class="excel-btn" onclick="setAllColumnsVisible(true)" style="font-size: 10px; padding: 2px 6px;">Select All</button>
                            <button class="excel-btn" onclick="setAllColumnsVisible(false)" style="font-size: 10px; padding: 2px 6px;">Deselect All</button>
                            <button class="excel-btn" onclick="applyColumnPreset('essential')" style="font-size: 10px; padding: 2px 6px;">Essential View</button>
                        </div>
                        <div class="col-picker-list" id="columnPickerList"></div>
                    </div>
                </div>

                <div style="margin-left: auto; display: flex; gap: 6px;">
                    <button class="excel-btn" onclick="triggerExport('xlsx')" title="Export Filtered Leads to Formatted Excel (.xlsx)">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                        Export .XLSX
                    </button>
                    <button class="excel-btn" onclick="triggerExport('csv')" title="Export CSV Data Sheet">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>
                        Export .CSV
                    </button>
                    <button class="excel-btn excel-btn-primary" onclick="openCRMModal()" title="Sync Leads to HubSpot, Zapier, or Webhooks">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z"/></svg>
                        CRM & Webhooks
                    </button>
                    <button class="excel-btn excel-btn-primary" onclick="loadChannels()">
                        <svg class="excel-icon" viewBox="0 0 24 24">
                            <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
                        </svg>
                        Refresh
                    </button>
                </div>
            </div>

            <!-- Line 2: Advanced Filter Controls -->
            <div class="data-filter-row" style="background-color: #e8e7e5; border-top: 1px solid #e1dfdd;">
                <div class="filter-group">
                    <span class="filter-label">Min Subs:</span>
                    <input type="number" id="filterMinSubs" class="formula-input" placeholder="e.g. 10000" style="width: 90px;" onchange="loadChannels(1)" />
                </div>

                <div class="filter-group">
                    <span class="filter-label">Max Subs:</span>
                    <input type="number" id="filterMaxSubs" class="formula-input" placeholder="e.g. 1M" style="width: 90px;" onchange="loadChannels(1)" />
                </div>

                <div class="filter-group">
                    <span class="filter-label">Min Views:</span>
                    <input type="number" id="filterMinViews" class="formula-input" placeholder="e.g. 50000" style="width: 90px;" onchange="loadChannels(1)" />
                </div>

                <div class="filter-group">
                    <span class="filter-label">Status:</span>
                    <select id="filterStatus" class="excel-dropdown" style="min-width: 95px;" onchange="loadChannels(1)">
                        <option value="">All Statuses</option>
                        <option value="Healthy">Healthy</option>
                        <option value="Active">Active</option>
                        <option value="Dormant">Dormant</option>
                        <option value="Revived">Revived</option>
                    </select>
                </div>

                <div class="filter-group">
                    <span class="filter-label">Region:</span>
                    <select id="filterRegion" class="excel-dropdown" style="min-width: 100px;" onchange="loadChannels(1)">
                        <option value="">All Regions</option>
                        <option value="US">United States (US)</option>
                        <option value="IN">India (IN)</option>
                        <option value="GB">United Kingdom (GB)</option>
                        <option value="CA">Canada (CA)</option>
                        <option value="AU">Australia (AU)</option>
                        <option value="DE">Germany (DE)</option>
                        <option value="FR">France (FR)</option>
                        <option value="JP">Japan (JP)</option>
                        <option value="BR">Brazil (BR)</option>
                    </select>
                </div>

                <div class="filter-group">
                    <span class="filter-label">Niche:</span>
                    <select id="filterNiche" class="excel-dropdown" style="min-width: 110px;" onchange="loadChannels(1)">
                        <option value="">All Niches</option>
                        <option value="Technology">Technology</option>
                        <option value="Gaming">Gaming</option>
                        <option value="Education">Education</option>
                        <option value="Entertainment">Entertainment</option>
                        <option value="Music">Music</option>
                        <option value="Cooking">Cooking</option>
                        <option value="Finance">Finance</option>
                        <option value="Lifestyle">Lifestyle</option>
                    </select>
                </div>

                <div class="filter-group">
                    <span class="filter-label">Quality:</span>
                    <select id="filterQuality" class="excel-dropdown" style="min-width: 95px;" onchange="loadChannels(1)">
                        <option value="">All Quality</option>
                        <option value="Excellent">Excellent</option>
                        <option value="Good">Good</option>
                        <option value="Average">Average</option>
                        <option value="Low">Low</option>
                    </select>
                </div>

                <div class="filter-group" style="margin-left: 4px;">
                    <label style="display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; color: var(--text-secondary); cursor: pointer;">
                        <input type="checkbox" id="filterHasEmail" onchange="loadChannels(1)" />
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                        Has Email
                    </label>
                </div>

                <div class="filter-group" style="margin-left: 4px;">
                    <label style="display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; color: var(--text-secondary); cursor: pointer;">
                        <input type="checkbox" id="filterHasSponsorship" onchange="loadChannels(1)" />
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg>
                        Sponsored
                    </label>
                </div>
            </div>

            <div class="grid-container">
                <div id="loadingDiv" class="loading-screen">
                    <div class="excel-spinner"></div>
                    <div>Parsing and sorting database table segments...</div>
                </div>
                
                <table id="channelsTable" class="excel-table" style="display: none;">
                    <thead>
<tr>
<th class="sticky-col">Avatar</th>
<th class="sortable" onclick="toggleSort('id')">Id <span></span></th>
<th class="sortable" onclick="toggleSort('run_id')">Run Id <span></span></th>
<th class="sortable" onclick="toggleSort('scraped_at')">Scraped At <span></span></th>
<th class="sortable" onclick="toggleSort('channel_id')">Channel Id <span></span></th>
<th class="sticky-col sortable" onclick="toggleSort('channel_name')">Channel Name <span></span></th>
<th class="sortable" onclick="toggleSort('description')">Description <span></span></th>
<th class="sortable" onclick="toggleSort('joined_date')">Joined Date <span></span></th>
<th class="sortable" onclick="toggleSort('country')">Country <span></span></th>
<th class="sortable" onclick="toggleSort('subscriber_count')">Subscriber Count <span></span></th>
<th class="sortable" onclick="toggleSort('total_views')">Total Views <span></span></th>
<th class="sortable" onclick="toggleSort('total_videos')">Total Videos <span></span></th>
<th class="sortable" onclick="toggleSort('email')">Email <span></span></th>
<th class="sortable" onclick="toggleSort('primary_category')">Primary Category <span></span></th>
<th class="sortable" onclick="toggleSort('cp_primary_niche')">Cp Primary Niche <span></span></th>
<th class="sortable" onclick="toggleSort('cp_secondary_niche')">Cp Secondary Niche <span></span></th>
<th class="sortable" onclick="toggleSort('cp_industry')">Cp Industry <span></span></th>
<th class="sortable" onclick="toggleSort('cp_target_audience')">Cp Target Audience <span></span></th>
<th class="sortable" onclick="toggleSort('cp_experience_level')">Cp Experience Level <span></span></th>
<th class="sortable" onclick="toggleSort('cp_primary_language')">Cp Primary Language <span></span></th>
<th class="sortable" onclick="toggleSort('cp_family_friendly')">Cp Family Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('cp_brand_friendly')">Cp Brand Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('cp_confidence')">Cp Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('q_professionalism')">Q Professionalism <span></span></th>
<th class="sortable" onclick="toggleSort('q_production_quality')">Q Production Quality <span></span></th>
<th class="sortable" onclick="toggleSort('q_branding')">Q Branding <span></span></th>
<th class="sortable" onclick="toggleSort('q_consistency')">Q Consistency <span></span></th>
<th class="sortable" onclick="toggleSort('q_originality')">Q Originality <span></span></th>
<th class="sortable" onclick="toggleSort('q_family_friendly')">Q Family Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('q_advertiser_friendly')">Q Advertiser Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('q_confidence')">Q Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('sp_has_sponsorships')">Sp Has Sponsorships <span></span></th>
<th class="sortable" onclick="toggleSort('sp_affiliate_links')">Sp Affiliate Links <span></span></th>
<th class="sortable" onclick="toggleSort('sp_business_email')">Sp Business Email <span></span></th>
<th class="sortable" onclick="toggleSort('sp_readiness')">Sp Readiness <span></span></th>
<th class="sortable" onclick="toggleSort('sp_confidence')">Sp Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('aud_gender_split')">Aud Gender Split <span></span></th>
<th class="sortable" onclick="toggleSort('aud_buying_intent')">Aud Buying Intent <span></span></th>
<th class="sortable" onclick="toggleSort('aud_audience_type')">Aud Audience Type <span></span></th>
<th class="sortable" onclick="toggleSort('aud_skill_level')">Aud Skill Level <span></span></th>
<th class="sortable" onclick="toggleSort('aud_spending_power')">Aud Spending Power <span></span></th>
<th class="sortable" onclick="toggleSort('aud_community_strength')">Aud Community Strength <span></span></th>
<th class="sortable" onclick="toggleSort('aud_confidence')">Aud Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('br_confidence')">Br Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('act_status')">Act Status <span></span></th>
<th class="sortable" onclick="toggleSort('act_score')">Act Score <span></span></th>
<th class="sortable" onclick="toggleSort('act_consistency_score')">Act Consistency Score <span></span></th>
<th class="sortable" onclick="toggleSort('act_revived')">Act Revived <span></span></th>
<th class="sortable" onclick="toggleSort('act_last_upload_days')">Act Last Upload Days <span></span></th>
<th class="sortable" onclick="toggleSort('act_uploads_30d')">Act Uploads 30d <span></span></th>
<th class="sortable" onclick="toggleSort('act_uploads_90d')">Act Uploads 90d <span></span></th>
<th class="sortable" onclick="toggleSort('act_uploads_1y')">Act Uploads 1y <span></span></th>
<th class="sortable" onclick="toggleSort('act_avg_duration_min')">Act Avg Duration Min <span></span></th>
<th class="sortable" onclick="toggleSort('act_expected_gap_days')">Act Expected Gap Days <span></span></th>
<th class="sortable" onclick="toggleSort('act_actual_gap_days')">Act Actual Gap Days <span></span></th>
<th class="sortable" onclick="toggleSort('act_upload_frequency')">Act Upload Frequency <span></span></th>
<th class="sortable" onclick="toggleSort('act_frequency_ratio')">Act Frequency Ratio <span></span></th>
</tr>
</thead>
                    <tbody id="channelsBody"></tbody>
                </table>
            </div>

            <div class="sheet-footer">
                <span class="sheet-info-text" id="record-count-info">Showing rows 0-0 of 0</span>
                <div class="pagination-controls" id="pagination"></div>
        </section>

        <section id="scraper-sheet" class="sheet-content">
            <div class="ops-container">
                <div class="ops-grid">
                    <!-- Manual Extraction Card -->
                    <div class="ops-card">
                        <div class="ops-card-header">
                            <span class="ops-card-title">
                                <svg class="excel-icon" viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 14z"/></svg>
                                On-Demand Extraction Engine
                            </span>
                        </div>
                        <div class="ops-card-body">
                            <!-- Quick Presets -->
                            <div>
                                <div class="ops-section-title">
                                    <svg class="excel-icon" viewBox="0 0 24 24"><path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.58-5.42L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/></svg>
                                    One-Click Scrape Presets
                                </div>
                                <div class="preset-chips">
                                    <button class="preset-chip" onclick="applyPreset('tech_saas')">🔥 Tech & SaaS Leads</button>
                                    <button class="preset-chip" onclick="applyPreset('gaming_india')">🎮 India Gaming Creators</button>
                                    <button class="preset-chip" onclick="applyPreset('finance_investing')">💼 Finance & Investing</button>
                                    <button class="preset-chip" onclick="applyPreset('sponsored_leads')">🎯 Sponsored Channel Leads</button>
                                </div>
                            </div>

                            <!-- Extraction Method & Target -->
                            <div style="display: flex; gap: 12px;">
                                <div style="flex: 1;">
                                    <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 700; color: var(--text-secondary);">Extraction Method</label>
                                    <select id="scrapeMethod" class="excel-dropdown" style="width: 100%;">
                                        <option value="search">Keyword Search</option>
                                        <option value="handle">Direct Handle</option>
                                    </select>
                                </div>
                                <div style="flex: 1;">
                                    <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 700; color: var(--text-secondary);">Search Target</label>
                                    <select id="scrapeTarget" class="excel-dropdown" style="width: 100%;">
                                        <option value="video">Videos</option>
                                        <option value="channel">Channels</option>
                                        <option value="live">Active Live Streams</option>
                                    </select>
                                </div>
                                <div style="flex: 2;">
                                    <label id="scrapeInputLabel" style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 700; color: var(--text-secondary);">Keyword / Handle</label>
                                    <input type="text" id="scrapeInput" class="formula-input" placeholder="e.g. gta 5 OR @MrBeast">
                                </div>
                            </div>

                            <!-- Detailed Search Filter Options -->
                            <div id="searchOptions" style="display: flex; flex-direction: column; gap: 12px; background: #faf9f8; padding: 12px; border-radius: 4px; border: 1px solid var(--excel-border);">
                                <div style="display: flex; gap: 12px;">
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Sort By</label>
                                        <select id="scrapeSort" class="excel-dropdown" style="width: 100%;">
                                            <option value="relevance">Relevance</option>
                                            <option value="popular">Popular</option>
                                            <option value="new">New</option>
                                        </select>
                                    </div>
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Region</label>
                                        <select id="scrapeRegion" class="excel-dropdown" style="width: 100%;">
                                            <option value="">Global (None)</option>
                                            <option value="usa">USA</option>
                                            <option value="uk">UK</option>
                                            <option value="india">India</option>
                                            <option value="canada">Canada</option>
                                            <option value="australia">Australia</option>
                                            <option value="germany">Germany</option>
                                            <option value="france">France</option>
                                            <option value="japan">Japan</option>
                                            <option value="brazil">Brazil</option>
                                            <option value="mexico">Mexico</option>
                                        </select>
                                    </div>
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Language</label>
                                        <select id="scrapeLanguage" class="excel-dropdown" style="width: 100%;">
                                            <option value="">Global (Any)</option>
                                            <option value="en">English</option>
                                            <option value="es">Spanish</option>
                                            <option value="fr">French</option>
                                            <option value="de">German</option>
                                            <option value="hi">Hindi</option>
                                            <option value="ja">Japanese</option>
                                            <option value="pt">Portuguese</option>
                                            <option value="ru">Russian</option>
                                            <option value="zh-CN">Chinese (Simplified)</option>
                                        </select>
                                    </div>
                                </div>
                                <div style="display: flex; gap: 12px;">
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Safe Search</label>
                                        <select id="scrapeSafeSearch" class="excel-dropdown" style="width: 100%;">
                                            <option value="none">None</option>
                                            <option value="moderate" selected>Moderate</option>
                                            <option value="strict">Strict</option>
                                        </select>
                                    </div>
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Published After</label>
                                        <input type="date" id="scrapePubAfter" class="formula-input" style="padding-left: 8px;">
                                    </div>
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Published Before</label>
                                        <input type="date" id="scrapePubBefore" class="formula-input" style="padding-left: 8px;">
                                    </div>
                                    <div style="flex: 0.7;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Max Channels</label>
                                        <input type="number" id="scrapeMaxResults" class="formula-input" value="1" min="1" max="10" style="padding-left: 8px;">
                                    </div>
                                </div>
                                <div style="display: flex; gap: 12px;">
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Topic Category</label>
                                        <select id="scrapeTopic" class="excel-dropdown" style="width: 100%;">
                                            <option value="">Any</option>
                                            <option value="/m/04rlf">Music</option>
                                            <option value="/m/0bzvm2">Gaming</option>
                                            <option value="/m/06ntj">Sports</option>
                                            <option value="/m/02jjt">Entertainment</option>
                                            <option value="/m/019_rr">Lifestyle</option>
                                            <option value="/m/07c1v">Technology</option>
                                            <option value="/m/098wr">Society</option>
                                            <option value="/m/01k8wb">Knowledge</option>
                                        </select>
                                    </div>
                                    <div style="flex: 1;">
                                        <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 600;">Video Scan Depth</label>
                                        <input type="number" id="scrapeDepth" class="formula-input" value="20" min="1" max="50" style="padding-left: 8px;">
                                    </div>
                                </div>
                            </div>
                            
                            <!-- AI Pipeline & Deep Options -->
                            <div>
                                <div class="ops-section-title">
                                    <svg class="excel-icon" viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14zM7 10h2v7H7zm4-3h2v10h-2zm4 6h2v4h-2z"/></svg>
                                    AI Enrichment Analyzers
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 10px;">
                                    <div style="display: flex; gap: 12px; align-items: center; padding-bottom: 8px; border-bottom: 1px solid var(--border-color);">
                                        <label style="display:flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">
                                            <input type="checkbox" id="scrapeUseAI" checked onchange="toggleAiAnalyzers(this.checked)"> Use Gemini AI Pipeline
                                        </label>
                                    </div>
                                    <div style="display: flex; gap: 12px; align-items: center;" id="aiOptionsGroup">
                                        <label style="display:flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; cursor: pointer;">
                                            <input type="checkbox" id="scrapeDeep" checked onchange="document.getElementById('deepLimit').disabled = !this.checked"> Deep Video Analysis
                                        </label>
                                        <label style="display:flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary);">
                                            Limit: <input type="number" id="deepLimit" class="formula-input" value="3" min="1" style="width: 55px; padding-left: 6px;">
                                        </label>
                                    </div>
                                    <div class="ops-chip-group">
                                        <label class="ops-chip-label">
                                            <input type="checkbox" class="ai-toggle" value="profile" checked> Creator Profile
                                        </label>
                                        <label class="ops-chip-label">
                                            <input type="checkbox" class="ai-toggle" value="audience" checked> Audience Insights
                                        </label>
                                        <label class="ops-chip-label">
                                            <input type="checkbox" class="ai-toggle" value="brands" checked> Brand Presence
                                        </label>
                                        <label class="ops-chip-label">
                                            <input type="checkbox" class="ai-toggle" value="sponsorship" checked> Sponsorship Readiness
                                        </label>
                                        <label class="ops-chip-label">
                                            <input type="checkbox" class="ai-toggle" value="quality" checked> Quality Score
                                        </label>
                                    </div>
                                </div>
                            </div>

                            <!-- Competitor Benchmarking -->
                            <div style="display: flex; gap: 12px; align-items: center; background: #f3f2f1; padding: 8px 12px; border-radius: 4px; border: 1px solid var(--excel-border);">
                                <label style="display:flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; cursor: pointer;">
                                    <input type="checkbox" id="scrapeBench" onchange="document.getElementById('benchHandle').disabled = !this.checked"> Benchmark Against:
                                </label>
                                <input type="text" id="benchHandle" class="formula-input" placeholder="@competitor" disabled style="width: 150px; padding-left: 8px;">
                            </div>
                            
                            <!-- Action Controls & Console Output -->
                            <div style="display: flex; flex-direction: column; gap: 0; margin-top: 4px;">
                                <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                                    <button class="excel-btn excel-btn-primary" id="btnStartScrape" onclick="startScrape()" style="display: inline-flex; align-items: center; gap: 6px; padding: 6px 16px; font-weight: 600;">
                                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg> Start Extraction Job
                                    </button>
                                    <button class="excel-btn" id="btnStopScrape" onclick="stopScrape()" disabled style="color: #d83b01; border-color: #d83b01; display: none; padding: 6px 16px; font-weight: 600;">
                                        Stop Job
                                    </button>
                                </div>
                                <div class="console-header-toolbar">
                                    <span class="console-title">
                                        <svg viewBox="0 0 24 24" width="12" height="12" fill="#4ec9b0"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-5 14H4v-4h11v4zm0-5H4V9h11v4zm5 5h-4V9h4v9z"/></svg>
                                        Extraction Terminal Log
                                    </span>
                                    <div class="console-actions">
                                        <button class="console-btn" onclick="clearConsole('scrapeLogBox')" title="Clear Terminal Log">Clear</button>
                                        <button class="console-btn" onclick="copyConsole('scrapeLogBox')" title="Copy Logs to Clipboard">Copy</button>
                                        <button class="console-btn console-btn-primary" onclick="openFullscreenTerminal('scrapeLogBox', 'On-Demand Extraction Terminal')" title="Fullscreen Terminal">Expand ⤢</button>
                                    </div>
                                </div>
                                <div id="scrapeLogBox" class="ops-console-box">Terminal log output ready...</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Autorunner Daemon Card -->
                    <div class="ops-card">
                        <div class="ops-card-header">
                            <span class="ops-card-title">
                                <svg class="excel-icon" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"/></svg>
                                Background Autorunner Daemon
                            </span>
                            <span id="autorunStatusBadge" class="pulse-badge pulse-badge-inactive">
                                <span class="pulse-dot"></span>
                                <span id="autorunStatus">INACTIVE</span>
                            </span>
                        </div>
                        <div class="ops-card-body">
                            <p style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
                                The background daemon continuously monitors indexed channels and automatically rescrapes out-of-date entries exceeding your configured refresh threshold.
                            </p>
                            
                            <!-- Telemetry KPI Dashboard Cards -->
                            <div class="ops-kpi-grid">
                                <div class="ops-kpi-card">
                                    <span class="ops-kpi-num" id="telemetryChannels">-</span>
                                    <span class="ops-kpi-lbl">Channels</span>
                                </div>
                                <div class="ops-kpi-card">
                                    <span class="ops-kpi-num" id="telemetryVideos">-</span>
                                    <span class="ops-kpi-lbl">Videos</span>
                                </div>
                                <div class="ops-kpi-card">
                                    <span class="ops-kpi-num" style="color:#107c41;">99.4%</span>
                                    <span class="ops-kpi-lbl">Success</span>
                                </div>
                                <div class="ops-kpi-card">
                                    <span class="ops-kpi-num" style="color:var(--excel-blue);">OK</span>
                                    <span class="ops-kpi-lbl">API Quota</span>
                                </div>
                            </div>

                            <div style="background: #faf9f8; padding: 14px; border-radius: 4px; border: 1px solid var(--excel-border); display: flex; flex-direction: column; gap: 12px;">
                                <div>
                                    <label style="display:block; margin-bottom: 4px; font-size: 11px; font-weight: 700; color: var(--text-secondary);">Rescrape Threshold (Hours)</label>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <input type="number" id="autorunThreshold" class="formula-input" value="24" style="width: 110px; padding-left: 8px;">
                                        <span style="font-size: 11px; color: var(--text-secondary); font-weight: 600;">Hours</span>
                                    </div>
                                </div>
                                <div>
                                    <button class="excel-btn excel-btn-primary" id="btnToggleAutorun" onclick="toggleAutorun()" style="padding: 6px 16px; font-weight: 600;">
                                        Start Autorunner Daemon
                                    </button>
                                </div>
                            </div>
                            
                            <div style="display: flex; flex-direction: column; gap: 0; margin-top: 4px;">
                                <div class="console-header-toolbar">
                                    <span class="console-title">
                                        <svg viewBox="0 0 24 24" width="12" height="12" fill="#4ec9b0"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z"/></svg>
                                        Daemon Telemetry Log
                                    </span>
                                    <div class="console-actions">
                                        <button class="console-btn" onclick="clearConsole('autorunLogBox')" title="Clear Log">Clear</button>
                                        <button class="console-btn" onclick="copyConsole('autorunLogBox')" title="Copy Logs">Copy</button>
                                        <button class="console-btn console-btn-primary" onclick="openFullscreenTerminal('autorunLogBox', 'Daemon Telemetry Console')" title="Fullscreen Terminal">Expand ⤢</button>
                                    </div>
                                </div>
                                <div id="autorunLogBox" class="ops-console-box" style="min-height: 140px;">Daemon logs ready...</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Visual Analytics BI Sheet -->
        <section id="analytics-sheet" class="sheet-content" style="display: none; padding: 16px; overflow-y: auto;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; background: #ffffff; padding: 12px 18px; border-radius: 4px; border: 1px solid var(--excel-border);">
                <div>
                    <h2 style="font-size: 16px; font-weight: 700; color: var(--excel-blue); display: flex; align-items: center; gap: 8px;">
                        <svg class="excel-icon" viewBox="0 0 24 24" style="width: 20px; height: 20px; fill: var(--excel-blue);">
                            <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/>
                        </svg>
                        Executive Telemetry & Visual BI Dashboard
                    </h2>
                    <p style="font-size: 12px; color: var(--text-secondary); margin-top: 2px;">
                        Real-time analytical breakdown of niche market distribution, sponsorship readiness, and creator quality metrics.
                    </p>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="excel-btn excel-btn-primary" onclick="loadAnalyticsData()">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                        Refresh BI Metrics
                    </button>
                    <button class="excel-btn" onclick="window.print()" title="Print or Save C-Suite Executive Summary PDF">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-4 11H9v-5h6v5zm4-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-2-9H7v4h10V3z"/></svg>
                        Print Executive PDF
                    </button>
                </div>
            </div>

            <!-- KPI Metric Summary Tiles -->
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;">
                <div class="ops-kpi-card" style="background: white; border: 1px solid var(--excel-border); border-radius: 4px; padding: 14px;">
                    <span class="ops-kpi-num" id="biTotalChannels" style="font-size: 22px;">-</span>
                    <span class="ops-kpi-lbl">Total Channels Indexed</span>
                </div>
                <div class="ops-kpi-card" style="background: white; border: 1px solid var(--excel-border); border-radius: 4px; padding: 14px;">
                    <span class="ops-kpi-num" id="biAvgReadiness" style="color: #1056a0; font-size: 22px;">-</span>
                    <span class="ops-kpi-lbl">Avg Sponsorship Readiness</span>
                </div>
                <div class="ops-kpi-card" style="background: white; border: 1px solid var(--excel-border); border-radius: 4px; padding: 14px;">
                    <span class="ops-kpi-num" id="biSponsoredPct" style="color: #107c41; font-size: 22px;">-</span>
                    <span class="ops-kpi-lbl">% Channels Sponsored</span>
                </div>
                <div class="ops-kpi-card" style="background: white; border: 1px solid var(--excel-border); border-radius: 4px; padding: 14px;">
                    <span class="ops-kpi-num" id="biEmailPct" style="color: #d83b01; font-size: 22px;">-</span>
                    <span class="ops-kpi-lbl">% Verified Business Emails</span>
                </div>
            </div>

            <!-- Chart Visual Grid -->
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 16px;">
                <!-- Chart 1: Niche Distribution (Donut) -->
                <div style="background: #ffffff; border: 1px solid var(--excel-border); border-radius: 4px; padding: 16px; height: 320px; display: flex; flex-direction: column;">
                    <div style="font-weight: 700; font-size: 13px; color: #323130; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                        <span>Primary Niche & Category Market Share</span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Donut Distribution</span>
                    </div>
                    <div style="flex: 1; position: relative;">
                        <canvas id="nicheChart"></canvas>
                    </div>
                </div>

                <!-- Chart 2: Content Quality Classification (Bar) -->
                <div style="background: #ffffff; border: 1px solid var(--excel-border); border-radius: 4px; padding: 16px; height: 320px; display: flex; flex-direction: column;">
                    <div style="font-weight: 700; font-size: 13px; color: #323130; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                        <span>Content Quality Classification Breakdown</span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Production Quality</span>
                    </div>
                    <div style="flex: 1; position: relative;">
                        <canvas id="qualityChart"></canvas>
                    </div>
                </div>

                <!-- Chart 3: Sponsorship Readiness vs Upload Activity Scatter -->
                <div style="background: #ffffff; border: 1px solid var(--excel-border); border-radius: 4px; padding: 16px; height: 340px; display: flex; flex-direction: column;">
                    <div style="font-weight: 700; font-size: 13px; color: #323130; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                        <span>Sponsorship Readiness vs. Upload Activity Matrix</span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Target Opportunity Matrix</span>
                    </div>
                    <div style="flex: 1; position: relative;">
                        <canvas id="opportunityChart"></canvas>
                    </div>
                </div>

                <!-- Chart 4: Geographic Region Distribution (Horizontal Bar) -->
                <div style="background: #ffffff; border: 1px solid var(--excel-border); border-radius: 4px; padding: 16px; height: 340px; display: flex; flex-direction: column;">
                    <div style="font-weight: 700; font-size: 13px; color: #323130; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                        <span>Geographic & Regional Lead Distribution</span>
                        <span style="font-size: 11px; color: var(--text-secondary);">Top Countries</span>
                    </div>
                    <div style="flex: 1; position: relative;">
                        <canvas id="regionChart"></canvas>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <div id="channelModal" class="modal">
        <div class="modal-wrapper">
            <div class="modal-title-bar">
                <h2 id="modalTitle">Cell Details View - channel_analyzer.xlsx</h2>
                <button class="modal-close-btn" onclick="closeModal()">
                    <svg style="width: 18px; height: 18px; fill: currentColor;" viewBox="0 0 24 24">
                        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                    </svg>
                </button>
            </div>
            <div class="modal-main-content" id="modalBody">
                <div class="loading-screen">
                    <div class="excel-spinner"></div>
                    Parsing channel index data...
                </div>
            </div>
        </div>
    </div>

    <!-- Theme-matched Office/Excel Alert Modal -->
    <div id="winAlertModal" class="win-modal-backdrop">
        <div class="win-dialog-box" role="dialog" aria-modal="true">
            <div class="win-title-bar">
                <div class="win-title-bar-text">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
                    <span id="winAlertTitle">System Notification</span>
                </div>
                <button class="win-close-btn" onclick="closeWinAlert()">&#10005;</button>
            </div>
            <div class="win-dialog-body">
                <div id="winAlertIcon" class="win-icon"></div>
                <div id="winAlertMessage" class="win-msg-content"></div>
            </div>
            <div class="win-dialog-footer">
                <button class="win-btn win-btn-primary" id="winAlertOkBtn" onclick="closeWinAlert()">OK</button>
            </div>
        </div>
    </div>

    <!-- Theme-matched Office/Excel Prompt Modal -->
    <div id="winPromptModal" class="win-modal-backdrop">
        <div class="win-dialog-box" role="dialog" aria-modal="true">
            <div class="win-title-bar">
                <div class="win-title-bar-text">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                    <span id="winPromptTitle">User Input Required</span>
                </div>
                <button class="win-close-btn" onclick="closeWinPrompt(false)">&#10005;</button>
            </div>
            <div class="win-dialog-body" style="flex-direction: column; gap: 10px;">
                <div style="display: flex; gap: 12px; width: 100%; align-items: center;">
                    <div id="winPromptIcon" class="win-icon"></div>
                    <div id="winPromptMessage" class="win-msg-content"></div>
                </div>
                <input type="text" id="winPromptInput" class="win-input-field" />
            </div>
            <div class="win-dialog-footer">
                <button class="win-btn win-btn-secondary" id="winPromptCancelBtn" onclick="closeWinPrompt(false)">Cancel</button>
                <button class="win-btn win-btn-primary" id="winPromptOkBtn" onclick="closeWinPrompt(true)">OK</button>
            </div>
        </div>
    </div>

    <!-- CRM & Webhook Integration Hub Modal -->
    <div id="crmModal" class="win-modal-backdrop">
        <div class="win-dialog-box" style="max-width: 580px; width: 95%;">
            <div class="win-title-bar">
                <div class="win-title-bar-text">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z"/></svg>
                    <span>CRM & External Integration Hub</span>
                </div>
                <button class="win-close-btn" onclick="closeCRMModal()">&#10005;</button>
            </div>
            <div class="win-dialog-body" style="flex-direction: column; gap: 14px; padding: 16px;">
                <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4;">
                    Dispatch lead batches directly to external CRMs, Zapier webhooks, or sales outreach tools based on your currently active grid search filters.
                </div>

                <!-- Webhook Section -->
                <div style="background: #faf9f8; border: 1px solid var(--excel-border); border-radius: 4px; padding: 12px; display: flex; flex-direction: column; gap: 8px;">
                    <div style="font-weight: 700; font-size: 11px; color: var(--excel-blue); display: flex; align-items: center; gap: 6px;">
                        <svg class="excel-icon" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
                        Zapier / Make / n8n Webhook Dispatcher
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <input type="text" id="webhookUrlInput" class="formula-input" placeholder="https://hooks.zapier.com/hooks/catch/..." style="flex: 1;" />
                        <button class="excel-btn excel-btn-primary" onclick="dispatchWebhook()">Send Webhook</button>
                    </div>
                </div>

                <!-- HubSpot Section -->
                <div style="background: #faf9f8; border: 1px solid var(--excel-border); border-radius: 4px; padding: 12px; display: flex; flex-direction: column; gap: 8px;">
                    <div style="font-weight: 700; font-size: 11px; color: #ff7a59; display: flex; align-items: center; gap: 6px;">
                        <svg class="excel-icon" viewBox="0 0 24 24" style="fill:#ff7a59;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z"/></svg>
                        HubSpot Contacts Sync
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <input type="password" id="hubspotApiKeyInput" class="formula-input" placeholder="HubSpot Private App Access Token" style="flex: 1;" />
                        <button class="excel-btn" style="background: #ff7a59; color: white; border-color: #ff7a59;" onclick="syncHubSpot()">Push HubSpot</button>
                    </div>
                </div>

                <div id="crmStatusBox" class="ops-console-box" style="min-height: 60px; font-size: 11px; border: 1px solid var(--excel-border);">Integration telemetry output ready...</div>
            </div>
            <div class="win-dialog-footer">
                <button class="win-btn win-btn-secondary" onclick="closeCRMModal()">Close</button>
            </div>
        </div>
    </div>

    <!-- API Key Pool & Quota Manager Modal -->
    <div id="keyPoolModal" class="win-modal-backdrop">
        <div class="win-dialog-box" style="max-width: 600px; width: 95%;">
            <div class="win-title-bar">
                <div class="win-title-bar-text">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"/></svg>
                    <span>YouTube API Key Pool & Quota Rotator</span>
                </div>
                <button class="win-close-btn" onclick="closeKeyPoolModal()">&#10005;</button>
            </div>
            <div class="win-dialog-body" style="flex-direction: column; gap: 14px; padding: 16px;">
                <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4;">
                    Register multiple YouTube Data API v3 keys to automatically bypass daily 10,000 unit quota limits. The system automatically rotates to the next active key if a key reaches 403 quota exhaustion.
                </div>

                <!-- Active Keys List -->
                <div style="background: #faf9f8; border: 1px solid var(--excel-border); border-radius: 4px; padding: 12px; display: flex; flex-direction: column; gap: 8px;">
                    <div style="font-weight: 700; font-size: 11px; color: var(--excel-blue); display: flex; align-items: center; justify-content: space-between;">
                        <span>Registered Rotation Pool Keys</span>
                        <button class="excel-btn" style="font-size: 10px; padding: 2px 6px;" onclick="loadKeyPoolStatus()">Refresh Pool</button>
                    </div>
                    <div id="keyPoolList" style="max-height: 140px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;"></div>
                </div>

                <!-- Add New Key Section -->
                <div style="background: #faf9f8; border: 1px solid var(--excel-border); border-radius: 4px; padding: 12px; display: flex; flex-direction: column; gap: 8px;">
                    <div style="font-weight: 700; font-size: 11px; color: var(--text-main);">
                        + Add New API Key to Pool
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <input type="text" id="newApiKeyInput" class="formula-input" placeholder="AIzaSy..." style="flex: 1;" />
                        <button class="excel-btn excel-btn-primary" onclick="addApiKeyToPool()">Register Key</button>
                    </div>
                </div>
            </div>
            <div class="win-dialog-footer">
                <button class="win-btn win-btn-secondary" onclick="closeKeyPoolModal()">Close</button>
            </div>
        </div>
    </div>

    <!-- Windows Fullscreen Developer Terminal Modal -->
    <div id="terminalModal" class="fullscreen-terminal-modal">
        <div class="terminal-modal-window">
            <div class="win-term-header">
                <div class="win-term-title-group">
                    <svg class="win-term-icon" viewBox="0 0 24 24" width="16" height="16" fill="#cccccc">
                        <path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-8 14H4v-2h8v2zm7.71-4.71l-4 4a.996.996 0 0 1-1.41 0l-4-4a.996.996 0 1 1 1.41-1.41L11 15.09l3.29-3.29c.39-.39 1.02-.39 1.41 0s.39 1.02 0 1.41z"/>
                    </svg>
                    <span id="terminalModalTitle" class="win-term-title">Administrator: Command Prompt - YouTube Scraper Telemetry Engine</span>
                </div>
                
                <div class="win-term-right-controls">
                    <div class="win-term-actions">
                        <button class="win-term-action-btn" onclick="clearModalTerminal()">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M15 16h4v2h-4zm0-8h7v2h-7zm0 4h6v2h-6zM3 18c0 1.1.9 2 2 2h6c1.1 0 2-.9 2-2V8H3v10zM14 5h-3l-1-1H6L5 5H2v2h12z"/></svg>
                            Clear
                        </button>
                        <button class="win-term-action-btn" onclick="copyModalTerminal()">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
                            Copy
                        </button>
                    </div>

                    <div class="win-window-buttons">
                        <button class="win-caption-btn win-min-btn" onclick="closeFullscreenTerminal()" title="Minimize">&#x2015;</button>
                        <button class="win-caption-btn win-max-btn" onclick="toggleTerminalWindowSize()" title="Maximize / Restore">&#x25A2;</button>
                        <button class="win-caption-btn win-close-btn" onclick="closeFullscreenTerminal()" title="Close Terminal (Esc)">&#x2715;</button>
                    </div>
                </div>
            </div>
            
            <div class="terminal-modal-body">
                <div class="win-term-banner">
                    Microsoft Windows [Version 10.0.22631.3880]<br>
                    (c) Microsoft Corporation. All rights reserved.<br><br>
                    C:\Projects\Youtube-Lead-Generator&gt; python web.py --telemetry-console<br>
                </div>
                <pre id="terminalModalLogContent" class="terminal-full-output">Initializing telemetry stream...</pre>
            </div>
        </div>
    </div>

    <script>
        // --- Theme-matched Office/Excel Dialog System ---
        const WIN_ICONS = {
            warning: `<svg viewBox="0 0 24 24" width="32" height="32" fill="#d97706"><path d="M12 2L1 21h22L12 2zm0 3.45L20.15 19H3.85L12 5.45zM11 10h2v4h-2v-4zm0 6h2v2h-2v-2z"/></svg>`,
            error: `<svg viewBox="0 0 24 24" width="32" height="32" fill="#d13438"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>`,
            info: `<svg viewBox="0 0 24 24" width="32" height="32" fill="#1056a0"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>`,
            question: `<svg viewBox="0 0 24 24" width="32" height="32" fill="#1056a0"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 16h-2v-2h2v2zm1.07-7.75l-.9.92C12.45 11.9 12 12.5 12 14h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>`
        };

        window._winAlertCallback = null;
        window._winPromptResolver = null;

        function showWinAlert(msg, title = "System Warning", type = "warning", callback = null) {
            const modal = document.getElementById('winAlertModal');
            const msgEl = document.getElementById('winAlertMessage');
            const titleEl = document.getElementById('winAlertTitle');
            const iconEl = document.getElementById('winAlertIcon');
            const okBtn = document.getElementById('winAlertOkBtn');
            
            if (!modal) return;
            
            msgEl.textContent = msg;
            titleEl.textContent = title;
            iconEl.innerHTML = WIN_ICONS[type] || WIN_ICONS.warning;
            
            modal.classList.add('active');
            okBtn.focus();
            
            window._winAlertCallback = callback;
        }

        function closeWinAlert() {
            const modal = document.getElementById('winAlertModal');
            if (modal) modal.classList.remove('active');
            if (typeof window._winAlertCallback === 'function') {
                const cb = window._winAlertCallback;
                window._winAlertCallback = null;
                cb();
            }
        }

        function showWinPrompt(msg, title = "User Input", defaultValue = "") {
            return new Promise((resolve) => {
                const modal = document.getElementById('winPromptModal');
                const msgEl = document.getElementById('winPromptMessage');
                const titleEl = document.getElementById('winPromptTitle');
                const iconEl = document.getElementById('winPromptIcon');
                const inputEl = document.getElementById('winPromptInput');
                
                if (!modal) return resolve(null);
                
                msgEl.textContent = msg;
                titleEl.textContent = title;
                iconEl.innerHTML = WIN_ICONS.question;
                inputEl.value = defaultValue;
                
                modal.classList.add('active');
                inputEl.focus();
                inputEl.select();
                
                window._winPromptResolver = resolve;
            });
        }

        function closeWinPrompt(isOk) {
            const modal = document.getElementById('winPromptModal');
            const inputEl = document.getElementById('winPromptInput');
            if (modal) modal.classList.remove('active');
            
            if (typeof window._winPromptResolver === 'function') {
                const res = window._winPromptResolver;
                window._winPromptResolver = null;
                res(isOk ? inputEl.value : null);
            }
        }

        // Add keyboard Enter / Escape listener for Nostalgic Windows Modals
        document.addEventListener('keydown', (e) => {
            const alertModal = document.getElementById('winAlertModal');
            const promptModal = document.getElementById('winPromptModal');
            
            if (alertModal && alertModal.classList.contains('active')) {
                if (e.key === 'Enter' || e.key === 'Escape') {
                    e.preventDefault();
                    closeWinAlert();
                }
            } else if (promptModal && promptModal.classList.contains('active')) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    closeWinPrompt(true);
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    closeWinPrompt(false);
                }
            }
        });

        // Override default browser alert
        window.alert = function(message) {
            showWinAlert(message, "System Message", "warning");
        };

        let currentPage = 1;
        let currentSearch = '';
        let currentSort = 'scraped_at';
        let currentPerPage = 50;

        function saveUIState(params) {
            try {
                const newUrl = window.location.pathname + '?' + params.toString();
                window.history.replaceState(null, '', newUrl);

                const stateObj = {};
                for (const [key, value] of params.entries()) {
                    if (value) stateObj[key] = value;
                }
                localStorage.setItem('yt_lead_generator_state', JSON.stringify(stateObj));
            } catch (e) {
                console.error("Failed to save UI state", e);
            }
        }

        function restoreUIState() {
            const urlParams = new URLSearchParams(window.location.search);
            let stateObj = {};

            if ([...urlParams.keys()].length > 0) {
                for (const [key, value] of urlParams.entries()) {
                    stateObj[key] = value;
                }
            } else {
                try {
                    const saved = localStorage.getItem('yt_lead_generator_state');
                    if (saved) stateObj = JSON.parse(saved);
                } catch (e) {
                    console.error("Failed to parse saved state", e);
                }
            }

            if (stateObj.search !== undefined && document.getElementById('searchInput')) {
                document.getElementById('searchInput').value = stateObj.search;
            }
            if (stateObj.sort_by && document.getElementById('sortBy')) {
                document.getElementById('sortBy').value = stateObj.sort_by;
            }
            if (stateObj.order && document.getElementById('sortOrder')) {
                document.getElementById('sortOrder').value = stateObj.order;
            }
            if (stateObj.per_page && document.getElementById('perPage')) {
                document.getElementById('perPage').value = stateObj.per_page;
            }
            if (stateObj.min_subs !== undefined && document.getElementById('filterMinSubs')) {
                document.getElementById('filterMinSubs').value = stateObj.min_subs;
            }
            if (stateObj.max_subs !== undefined && document.getElementById('filterMaxSubs')) {
                document.getElementById('filterMaxSubs').value = stateObj.max_subs;
            }
            if (stateObj.min_views !== undefined && document.getElementById('filterMinViews')) {
                document.getElementById('filterMinViews').value = stateObj.min_views;
            }
            if (stateObj.max_views !== undefined && document.getElementById('filterMaxViews')) {
                document.getElementById('filterMaxViews').value = stateObj.max_views;
            }
            if (stateObj.act_status !== undefined && document.getElementById('filterStatus')) {
                document.getElementById('filterStatus').value = stateObj.act_status;
            }
            if (stateObj.region !== undefined && document.getElementById('filterRegion')) {
                document.getElementById('filterRegion').value = stateObj.region;
            }
            if (stateObj.niche !== undefined && document.getElementById('filterNiche')) {
                document.getElementById('filterNiche').value = stateObj.niche;
            }
            if (stateObj.quality !== undefined && document.getElementById('filterQuality')) {
                document.getElementById('filterQuality').value = stateObj.quality;
            }
            if (document.getElementById('filterHasEmail')) {
                document.getElementById('filterHasEmail').checked = stateObj.has_email === '1';
            }
            if (document.getElementById('filterHasSponsorship')) {
                document.getElementById('filterHasSponsorship').checked = stateObj.has_sponsorship === '1';
            }
            if (stateObj.sheet) {
                const targetSheet = document.getElementById(stateObj.sheet);
                if (targetSheet) {
                    const tabBtn = document.querySelector(`.sheet-tab[onclick*="${stateObj.sheet}"]`);
                    if (tabBtn) switchSheet(stateObj.sheet, tabBtn, false);
                }
            }

            return parseInt(stateObj.page) || 1;
        }

        function switchSheet(sheetId, tabBtn, triggerReload = true) {
            const contents = document.querySelectorAll('.sheet-content');
            contents.forEach(c => c.classList.remove('active'));

            const tabs = document.querySelectorAll('.sheet-tab');
            tabs.forEach(t => {
                t.classList.remove('active');
                t.querySelector('.excel-icon').style.fill = 'var(--text-secondary)';
            });

            document.getElementById(sheetId).classList.add('active');
            tabBtn.classList.add('active');
            tabBtn.querySelector('.excel-icon').style.fill = 'var(--excel-blue)';

            if (triggerReload && sheetId === 'channels-sheet') {
                loadChannels(currentPage);
            }
        }

        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                document.getElementById('totalChannels').textContent = data.total_channels.toLocaleString();
                document.getElementById('totalRuns').textContent = data.total_runs.toLocaleString();
                document.getElementById('totalVideos').textContent = data.total_videos.toLocaleString();
                if (document.getElementById('telemetryChannels')) document.getElementById('telemetryChannels').textContent = data.total_channels.toLocaleString();
                if (document.getElementById('telemetryVideos')) document.getElementById('telemetryVideos').textContent = data.total_videos.toLocaleString();
                
                if (data.latest_scrape) {
                    const date = new Date(data.latest_scrape);
                    document.getElementById('latestScrape').textContent = date.toLocaleDateString();
                } else {
                    document.getElementById('latestScrape').textContent = '-';
                }
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }

        function resetFilters() {
            if (document.getElementById('sortBy')) document.getElementById('sortBy').value = 'scraped_at';
            if (document.getElementById('sortOrder')) document.getElementById('sortOrder').value = 'DESC';
            if (document.getElementById('perPage')) document.getElementById('perPage').value = '50';
            if (document.getElementById('filterMinSubs')) document.getElementById('filterMinSubs').value = '';
            if (document.getElementById('filterMaxSubs')) document.getElementById('filterMaxSubs').value = '';
            if (document.getElementById('filterMinViews')) document.getElementById('filterMinViews').value = '';
            if (document.getElementById('filterMaxViews')) document.getElementById('filterMaxViews').value = '';
            if (document.getElementById('filterStatus')) document.getElementById('filterStatus').value = '';
            if (document.getElementById('filterRegion')) document.getElementById('filterRegion').value = '';
            if (document.getElementById('filterNiche')) document.getElementById('filterNiche').value = '';
            if (document.getElementById('filterQuality')) document.getElementById('filterQuality').value = '';
            if (document.getElementById('filterHasEmail')) document.getElementById('filterHasEmail').checked = false;
            if (document.getElementById('filterHasSponsorship')) document.getElementById('filterHasSponsorship').checked = false;
            if (document.getElementById('searchInput')) document.getElementById('searchInput').value = '';
            localStorage.removeItem('yt_lead_generator_state');
            window.history.replaceState(null, '', window.location.pathname);
            loadChannels(1);
        }

        async function loadChannels(page = 1) {
            currentPage = page;
            document.getElementById('loadingDiv').style.display = 'block';
            document.getElementById('channelsTable').style.display = 'none';

            try {
                currentSort = document.getElementById('sortBy')?.value || 'scraped_at';
                const sortOrder = document.getElementById('sortOrder')?.value || 'DESC';
                currentPerPage = document.getElementById('perPage')?.value || 50;
                currentSearch = document.getElementById('searchInput')?.value.trim() || '';

                const minSubs = document.getElementById('filterMinSubs')?.value || '';
                const maxSubs = document.getElementById('filterMaxSubs')?.value || '';
                const minViews = document.getElementById('filterMinViews')?.value || '';
                const maxViews = document.getElementById('filterMaxViews')?.value || '';
                const status = document.getElementById('filterStatus')?.value || '';
                const region = document.getElementById('filterRegion')?.value || '';
                const niche = document.getElementById('filterNiche')?.value || '';
                const quality = document.getElementById('filterQuality')?.value || '';
                const hasEmail = document.getElementById('filterHasEmail')?.checked ? '1' : '';
                const hasSponsorship = document.getElementById('filterHasSponsorship')?.checked ? '1' : '';
                const activeSheet = document.querySelector('.sheet-content.active')?.id || 'channels-sheet';

                const params = new URLSearchParams();
                params.set('page', currentPage);
                params.set('per_page', currentPerPage);
                if (currentSearch) params.set('search', currentSearch);
                if (currentSort) params.set('sort_by', currentSort);
                if (sortOrder) params.set('order', sortOrder);
                if (minSubs) params.set('min_subs', minSubs);
                if (maxSubs) params.set('max_subs', maxSubs);
                if (minViews) params.set('min_views', minViews);
                if (maxViews) params.set('max_views', maxViews);
                if (status) params.set('act_status', status);
                if (region) params.set('region', region);
                if (niche) params.set('niche', niche);
                if (quality) params.set('quality', quality);
                if (hasEmail) params.set('has_email', hasEmail);
                if (hasSponsorship) params.set('has_sponsorship', hasSponsorship);
                if (activeSheet) params.set('sheet', activeSheet);

                saveUIState(params);

                const response = await fetch(`/api/channels?${params.toString()}`);
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || `HTTP error status: ${response.status}`);
                }
                
                const data = await response.json();

                displayChannels(data.channels);
                displayPagination(data);

                document.getElementById('loadingDiv').style.display = 'none';
                document.getElementById('channelsTable').style.display = 'table';
            } catch (error) {
                console.error('Error loading channels:', error);
                document.getElementById('loadingDiv').innerHTML = `
                    <div class="error-message">
                        <strong>Error Parsing Database Tables:</strong> ${escapeHtml(error.message)}
                        <p style="margin-top: 10px; font-size: 11px;">Verify API configurations and inspect diagnostic console logs.</p>
                        <button class="excel-btn excel-btn-primary" style="margin-top: 12px;" onclick="location.reload()">Reload Console Workbook</button>
                    </div>
                `;
            }
        }

        // --- Column Selection / Visibility Management ---
        const COLUMN_NAMES = [
            "Avatar", "ID", "Run ID", "Scraped At", "Channel ID", "Channel Name", "Description", "Joined Date",
            "Country", "Subscriber Count", "Total Views", "Total Videos", "Email", "Primary Category",
            "CP Primary Niche", "CP Secondary Niche", "CP Industry", "CP Target Audience", "CP Experience Level",
            "CP Primary Language", "CP Family Friendly", "CP Brand Friendly", "CP Confidence",
            "Q Professionalism", "Q Production Quality", "Q Branding", "Q Consistency", "Q Originality",
            "Q Family Friendly", "Q Advertiser Friendly", "Q Confidence",
            "SP Has Sponsorships", "SP Affiliate Links", "SP Business Email", "SP Readiness", "SP Confidence",
            "AUD Gender Split", "AUD Buying Intent", "AUD Audience Type", "AUD Skill Level", "AUD Spending Power",
            "AUD Community Strength", "AUD Confidence", "BR Confidence",
            "ACT Status", "ACT Score", "ACT Consistency Score", "ACT Revived", "ACT Last Upload Days",
            "ACT Uploads 30d", "ACT Uploads 90d", "ACT Uploads 1y", "ACT Avg Duration Min",
            "ACT Expected Gap Days", "ACT Actual Gap Days", "ACT Upload Frequency", "ACT Frequency Ratio"
        ];

        let hiddenColumns = new Set();

        function initColumnPicker() {
            const listEl = document.getElementById('columnPickerList');
            if (!listEl) return;

            try {
                const saved = localStorage.getItem('yt_lead_hidden_cols');
                if (saved) {
                    hiddenColumns = new Set(JSON.parse(saved));
                }
            } catch(e) {}

            listEl.innerHTML = '';
            COLUMN_NAMES.forEach((colName, idx) => {
                const isChecked = !hiddenColumns.has(idx);
                const label = document.createElement('label');
                label.className = 'col-picker-item';
                label.dataset.colName = colName.toLowerCase();
                label.innerHTML = `
                    <input type="checkbox" value="${idx}" ${isChecked ? 'checked' : ''} onchange="toggleColumnVisibility(${idx}, this.checked)">
                    <span>${colName}</span>
                `;
                listEl.appendChild(label);
            });

            applyColumnVisibilities();
            updatePickerLabel();
        }

        function toggleColumnPicker(event) {
            if (event) event.stopPropagation();
            const menu = document.getElementById('columnPickerMenu');
            if (menu) menu.classList.toggle('active');
        }

        document.addEventListener('click', (e) => {
            const menu = document.getElementById('columnPickerMenu');
            const btn = document.getElementById('colPickerBtn');
            if (menu && menu.classList.contains('active') && !menu.contains(e.target) && !btn?.contains(e.target)) {
                menu.classList.remove('active');
            }
        });

        function filterPickerColumns() {
            const query = document.getElementById('colSearchInput')?.value.toLowerCase().trim() || '';
            const items = document.querySelectorAll('#columnPickerList .col-picker-item');
            items.forEach(item => {
                const name = item.dataset.colName;
                if (!query || name.includes(query)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        }

        function toggleColumnVisibility(colIdx, isVisible) {
            if (isVisible) {
                hiddenColumns.delete(colIdx);
            } else {
                hiddenColumns.add(colIdx);
            }
            saveColumnState();
            applyColumnVisibilities();
            updatePickerLabel();
        }

        function setAllColumnsVisible(visible) {
            const checkboxes = document.querySelectorAll('#columnPickerList input[type="checkbox"]');
            hiddenColumns.clear();
            checkboxes.forEach((cb, idx) => {
                cb.checked = visible;
                if (!visible) hiddenColumns.add(idx);
            });
            saveColumnState();
            applyColumnVisibilities();
            updatePickerLabel();
        }

        function applyColumnPreset(preset) {
            const essentialIndices = [0, 1, 3, 5, 8, 9, 10, 11, 12, 14, 24, 34, 44];
            const checkboxes = document.querySelectorAll('#columnPickerList input[type="checkbox"]');
            hiddenColumns.clear();

            checkboxes.forEach((cb, idx) => {
                const isEssential = essentialIndices.includes(idx);
                cb.checked = isEssential;
                if (!isEssential) hiddenColumns.add(idx);
            });

            saveColumnState();
            applyColumnVisibilities();
            updatePickerLabel();
        }

        function saveColumnState() {
            localStorage.setItem('yt_lead_hidden_cols', JSON.stringify([...hiddenColumns]));
        }

        function applyColumnVisibilities() {
            const table = document.getElementById('channelsTable');
            if (!table) return;

            const ths = table.querySelectorAll('thead tr th');
            ths.forEach((th, idx) => {
                th.style.display = hiddenColumns.has(idx) ? 'none' : '';
            });

            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const tds = row.querySelectorAll('td');
                tds.forEach((td, idx) => {
                    td.style.display = hiddenColumns.has(idx) ? 'none' : '';
                });
            });
        }

        function updatePickerLabel() {
            const total = COLUMN_NAMES.length;
            const visible = total - hiddenColumns.size;
            const label = document.getElementById('colPickerLabel');
            if (label) {
                label.textContent = `Columns (${visible}/${total})`;
            }
        }

        // Attach Enter key event listener to search input
        document.addEventListener('DOMContentLoaded', () => {
            document.getElementById('searchInput')?.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    loadChannels(1);
                }
            });
            initColumnPicker();
        });

        // Initialize state from URL / Storage on startup
        const initialPage = restoreUIState();
        initColumnPicker();
        loadStats();
        loadChannels(initialPage);

                function formatNumber(num) {
            if (num === null || num === undefined) return '';
            const n = Number(num);
            if (isNaN(n)) return num;
            return n.toLocaleString();
        }

        
        function toggleColumn(checkbox) {
            const index = parseInt(checkbox.value);
            const display = checkbox.checked ? '' : 'none';
            const table = document.getElementById('dataTable');
            const th = table.querySelector(`thead tr th:nth-child(${index + 1})`);
            if (th) th.style.display = display;
            
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const td = row.querySelector(`td:nth-child(${index + 1})`);
                if (td) td.style.display = display;
            });
        }

        function displayChannels(channels) {
            const tbody = document.getElementById('channelsBody');
            tbody.innerHTML = '';

            if (channels.length === 0) {
                tbody.innerHTML = `<tr><td colspan="57" style="text-align: center; color: var(--text-secondary); padding: 20px;">No matching records found</td></tr>`;
                return;
            }

            channels.forEach(channel => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td class="sticky-col">
                        <img src="https://unavatar.io/youtube/${escapeHtml(channel.handle || channel.channel_name)}?fallback=https://api.dicebear.com/7.x/initials/svg?seed=${escapeHtml(channel.channel_name)}" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; vertical-align: middle;" alt="Avatar">
                    </td>
                    <td>${escapeHtml(channel.id || '')}</td>
                    <td>${escapeHtml(channel.run_id || '')}</td>
                    <td>${escapeHtml(channel.scraped_at || '')}</td>
                    <td>${escapeHtml(channel.channel_id || '')}</td>
                    <td class="sticky-col"><span class="cell-action" onclick="window.open('/analysis/${channel.id}', '_blank')">${escapeHtml(channel.channel_name || '')}</span></td>
                    <td>${escapeHtml(channel.description || '')}</td>
                    <td>${escapeHtml(channel.joined_date || '')}</td>
                    <td>${formatNumber(channel.country)}</td>
                    <td>${formatNumber(channel.subscriber_count)}</td>
                    <td>${formatNumber(channel.total_views)}</td>
                    <td>${formatNumber(channel.total_videos)}</td>
                    <td>${escapeHtml(channel.email || '')}</td>
                    <td>${escapeHtml(channel.primary_category || '')}</td>
                    <td>${escapeHtml(channel.cp_primary_niche || '')}</td>
                    <td>${escapeHtml(channel.cp_secondary_niche || '')}</td>
                    <td>${escapeHtml(channel.cp_industry || '')}</td>
                    <td>${escapeHtml(channel.cp_target_audience || '')}</td>
                    <td>${formatNumber(channel.cp_experience_level)}</td>
                    <td>${escapeHtml(channel.cp_primary_language || '')}</td>
                    <td>${escapeHtml(channel.cp_family_friendly || '')}</td>
                    <td>${escapeHtml(channel.cp_brand_friendly || '')}</td>
                    <td>${formatNumber(channel.cp_confidence)}</td>
                    <td>${escapeHtml(channel.q_professionalism || '')}</td>
                    <td>${formatNumber(channel.q_production_quality)}</td>
                    <td>${escapeHtml(channel.q_branding || '')}</td>
                    <td>${escapeHtml(channel.q_consistency || '')}</td>
                    <td>${escapeHtml(channel.q_originality || '')}</td>
                    <td>${escapeHtml(channel.q_family_friendly || '')}</td>
                    <td>${escapeHtml(channel.q_advertiser_friendly || '')}</td>
                    <td>${formatNumber(channel.q_confidence)}</td>
                    <td>${escapeHtml(channel.sp_has_sponsorships || '')}</td>
                    <td>${escapeHtml(channel.sp_affiliate_links || '')}</td>
                    <td>${escapeHtml(channel.sp_business_email || '')}</td>
                    <td>${escapeHtml(channel.sp_readiness || '')}</td>
                    <td>${formatNumber(channel.sp_confidence)}</td>
                    <td>${formatNumber(channel.aud_gender_split)}</td>
                    <td>${escapeHtml(channel.aud_buying_intent || '')}</td>
                    <td>${escapeHtml(channel.aud_audience_type || '')}</td>
                    <td>${formatNumber(channel.aud_skill_level)}</td>
                    <td>${formatNumber(channel.aud_spending_power)}</td>
                    <td>${formatNumber(channel.aud_community_strength)}</td>
                    <td>${formatNumber(channel.aud_confidence)}</td>
                    <td>${formatNumber(channel.br_confidence)}</td>
                    <td>${escapeHtml(channel.act_status || '')}</td>
                    <td>${formatNumber(channel.act_score)}</td>
                    <td>${formatNumber(channel.act_consistency_score)}</td>
                    <td>${escapeHtml(channel.act_revived || '')}</td>
                    <td>${formatNumber(channel.act_last_upload_days)}</td>
                    <td>${escapeHtml(channel.act_uploads_30d || '')}</td>
                    <td>${escapeHtml(channel.act_uploads_90d || '')}</td>
                    <td>${escapeHtml(channel.act_uploads_1y || '')}</td>
                    <td>${formatNumber(channel.act_avg_duration_min)}</td>
                    <td>${formatNumber(channel.act_expected_gap_days)}</td>
                    <td>${formatNumber(channel.act_actual_gap_days)}</td>
                    <td>${escapeHtml(channel.act_upload_frequency || '')}</td>
                    <td>${formatNumber(channel.act_frequency_ratio)}</td>
                `;
                tbody.appendChild(row);
            });
            applyColumnVisibilities();
        }

        function displayPagination(data) {
            const pagination = document.getElementById('pagination');
            pagination.innerHTML = '';

            const totalPages = data.total_pages;
            const currentPage = data.page;

            const currentLimit = parseInt(document.getElementById('perPage').value);
            const startRange = ((currentPage - 1) * currentLimit) + 1;
            const endRange = Math.min(currentPage * currentLimit, data.total);
            
            document.getElementById('record-count-info').textContent = 
                data.total > 0 ? `Showing rows ${startRange}-${endRange} of ${data.total} parsed records` : `No records available`;

            const prevBtn = document.createElement('button');
            prevBtn.className = 'excel-page-btn';
            prevBtn.innerHTML = `<svg class="excel-icon" viewBox="0 0 24 24"><path d="M15.41 7.41L14 6l-6 6 6 6 1.54-1.41L10.83 12z"/></svg>`;
            prevBtn.disabled = currentPage === 1;
            prevBtn.onclick = () => loadChannels(currentPage - 1);
            pagination.appendChild(prevBtn);

            const startPage = Math.max(1, currentPage - 2);
            const endPage = Math.min(totalPages, currentPage + 2);

            if (startPage > 1) {
                const firstBtn = document.createElement('button');
                firstBtn.className = 'excel-page-btn';
                firstBtn.textContent = '1';
                firstBtn.onclick = () => loadChannels(1);
                pagination.appendChild(firstBtn);

                if (startPage > 2) {
                    const dots = document.createElement('span');
                    dots.textContent = '...';
                    dots.style.padding = '0 6px';
                    dots.style.color = 'var(--text-secondary)';
                    pagination.appendChild(dots);
                }
            }

            for (let i = startPage; i <= endPage; i++) {
                const pageBtn = document.createElement('button');
                pageBtn.className = 'excel-page-btn' + (i === currentPage ? ' active' : '');
                pageBtn.textContent = i;
                pageBtn.onclick = () => loadChannels(i);
                pagination.appendChild(pageBtn);
            }

            if (endPage < totalPages) {
                if (endPage < totalPages - 1) {
                    const dots = document.createElement('span');
                    dots.textContent = '...';
                    dots.style.padding = '0 6px';
                    pagination.appendChild(dots);
                }

                const lastBtn = document.createElement('button');
                lastBtn.className = 'excel-page-btn';
                lastBtn.textContent = totalPages;
                lastBtn.onclick = () => loadChannels(totalPages);
                pagination.appendChild(lastBtn);
            }

            const nextBtn = document.createElement('button');
            nextBtn.className = 'excel-page-btn';
            nextBtn.innerHTML = `<svg class="excel-icon" viewBox="0 0 24 24"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>`;
            nextBtn.disabled = currentPage === totalPages || totalPages === 0;
            nextBtn.onclick = () => loadChannels(currentPage + 1);
            pagination.appendChild(nextBtn);
        }

        async function viewChannel(channelRowId) {
            const modal = document.getElementById('channelModal');
            const modalBody = document.getElementById('modalBody');
            modalBody.innerHTML = `
                <div class="loading-screen">
                    <div class="excel-spinner"></div>
                    Executing schema relation queries for record ID: [${channelRowId}]...
                </div>
            `;
            modal.style.display = 'block';

            try {
                const response = await fetch(`/api/channel/${channelRowId}`);
                const data = await response.json();
                displayChannelDetails(data);
            } catch (error) {
                modalBody.innerHTML = `
                    <div class="error-message">
                        <strong>Relational Query Interrupted:</strong> Unable to process row references.
                    </div>
                `;
            }
        }

        function displayChannelDetails(data) {
            const channel = data.channel;
            const modalBody = document.getElementById('modalBody');
            
            let html = `
                <div class="inspector-sheet">
                    <div class="inspector-cell">
                        <div class="inspector-label">Channel Id</div>
                        <div class="inspector-value text-bold" style="color: var(--excel-blue);">${channel.id}</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Channel Name</div>
                        <div class="inspector-value">${escapeHtml(channel.channel_name)}</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Subscribers</div>
                        <div class="inspector-value cell-numeric" style="text-align: left;">${(channel.subscriber_count || 0).toLocaleString()}</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Total Views</div>
                        <div class="inspector-value cell-numeric" style="text-align: left;">${(channel.total_views || 0).toLocaleString()}</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Total Videos</div>
                        <div class="inspector-value cell-numeric" style="text-align: left;">${(channel.total_videos || 0).toLocaleString()}</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Activity Status</div>
                        <div class="inspector-value" style="padding-top: 4px;">${getActivityBadge(channel.act_status)}</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Activity Score</div>
                        <div class="inspector-value cell-numeric" style="text-align: left; font-weight: bold;">${channel.act_score || '-'}/100</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Primary Niche</div>
                        <div class="inspector-value">${escapeHtml(channel.cp_primary_niche || '-')}</div>
                    </div>
                    <div class="inspector-cell">
                        <div class="inspector-label">Quality Score</div>
                        <div class="inspector-value cell-numeric" style="text-align: left; color: var(--excel-blue); font-weight: bold;">${channel.q_production_quality || '-'}/10</div>
                    </div>
                </div>

                ${data.content_styles && data.content_styles.length > 0 ? `
                    <div style="margin-bottom: 16px;">
                        <span class="inspector-label" style="display:block; margin-bottom: 6px;">Scraped Content Styles</span>
                        <div class="tag-pill-container">
                            ${data.content_styles.map(s => `<span class="tag-pill">${escapeHtml(s)}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}

                ${data.brands && data.brands.length > 0 ? `
                    <div style="margin-bottom: 16px;">
                        <span class="inspector-label" style="display:block; margin-bottom: 6px;">Linked Advertisers & Brands Mentioned</span>
                        <div class="tag-pill-container">
                            ${data.brands.map(b => `<span class="tag-pill" style="background-color: #f3f2f1; color: #444; border-color: var(--excel-border);">${escapeHtml(b)}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}

                ${data.audience_age_groups && data.audience_age_groups.length > 0 ? `
                    <div style="margin-bottom: 16px;">
                        <span class="inspector-label" style="display:block; margin-bottom: 6px;">Estimated Demographics: Age Target Bands</span>
                        <div class="tag-pill-container">
                            ${data.audience_age_groups.map(a => `<span class="tag-pill">${escapeHtml(a)}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}

                ${data.audience_regions && data.audience_regions.length > 0 ? `
                    <div style="margin-bottom: 24px;">
                        <span class="inspector-label" style="display:block; margin-bottom: 6px;">Geographical Demographics (Regional Reach)</span>
                        <div class="tag-pill-container">
                            ${data.audience_regions.map(r => `<span class="tag-pill">${escapeHtml(r)}</span>`).join('')}
                        </div>
                    </div>
                ` : ''}

                ${data.videos && data.videos.length > 0 ? `
                    <div style="margin-top: 20px;">
                        <span class="inspector-label" style="display:block; margin-bottom: 10px;">Scraped Child Table Segment (Indexed Videos)</span>
                        <table class="excel-table" style="font-size: 11px;">
                            <thead>
<tr>
<th class="sticky-col">Avatar</th>
<th class="sortable" onclick="toggleSort('id')">Id <span></span></th>
<th class="sortable" onclick="toggleSort('run_id')">Run Id <span></span></th>
<th class="sortable" onclick="toggleSort('scraped_at')">Scraped At <span></span></th>
<th class="sortable" onclick="toggleSort('channel_id')">Channel Id <span></span></th>
<th class="sticky-col sortable" onclick="toggleSort('channel_name')">Channel Name <span></span></th>
<th class="sortable" onclick="toggleSort('description')">Description <span></span></th>
<th class="sortable" onclick="toggleSort('joined_date')">Joined Date <span></span></th>
<th class="sortable" onclick="toggleSort('country')">Country <span></span></th>
<th class="sortable" onclick="toggleSort('subscriber_count')">Subscriber Count <span></span></th>
<th class="sortable" onclick="toggleSort('total_views')">Total Views <span></span></th>
<th class="sortable" onclick="toggleSort('total_videos')">Total Videos <span></span></th>
<th class="sortable" onclick="toggleSort('email')">Email <span></span></th>
<th class="sortable" onclick="toggleSort('primary_category')">Primary Category <span></span></th>
<th class="sortable" onclick="toggleSort('cp_primary_niche')">Cp Primary Niche <span></span></th>
<th class="sortable" onclick="toggleSort('cp_secondary_niche')">Cp Secondary Niche <span></span></th>
<th class="sortable" onclick="toggleSort('cp_industry')">Cp Industry <span></span></th>
<th class="sortable" onclick="toggleSort('cp_target_audience')">Cp Target Audience <span></span></th>
<th class="sortable" onclick="toggleSort('cp_experience_level')">Cp Experience Level <span></span></th>
<th class="sortable" onclick="toggleSort('cp_primary_language')">Cp Primary Language <span></span></th>
<th class="sortable" onclick="toggleSort('cp_family_friendly')">Cp Family Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('cp_brand_friendly')">Cp Brand Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('cp_confidence')">Cp Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('q_professionalism')">Q Professionalism <span></span></th>
<th class="sortable" onclick="toggleSort('q_production_quality')">Q Production Quality <span></span></th>
<th class="sortable" onclick="toggleSort('q_branding')">Q Branding <span></span></th>
<th class="sortable" onclick="toggleSort('q_consistency')">Q Consistency <span></span></th>
<th class="sortable" onclick="toggleSort('q_originality')">Q Originality <span></span></th>
<th class="sortable" onclick="toggleSort('q_family_friendly')">Q Family Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('q_advertiser_friendly')">Q Advertiser Friendly <span></span></th>
<th class="sortable" onclick="toggleSort('q_confidence')">Q Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('sp_has_sponsorships')">Sp Has Sponsorships <span></span></th>
<th class="sortable" onclick="toggleSort('sp_affiliate_links')">Sp Affiliate Links <span></span></th>
<th class="sortable" onclick="toggleSort('sp_business_email')">Sp Business Email <span></span></th>
<th class="sortable" onclick="toggleSort('sp_readiness')">Sp Readiness <span></span></th>
<th class="sortable" onclick="toggleSort('sp_confidence')">Sp Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('aud_gender_split')">Aud Gender Split <span></span></th>
<th class="sortable" onclick="toggleSort('aud_buying_intent')">Aud Buying Intent <span></span></th>
<th class="sortable" onclick="toggleSort('aud_audience_type')">Aud Audience Type <span></span></th>
<th class="sortable" onclick="toggleSort('aud_skill_level')">Aud Skill Level <span></span></th>
<th class="sortable" onclick="toggleSort('aud_spending_power')">Aud Spending Power <span></span></th>
<th class="sortable" onclick="toggleSort('aud_community_strength')">Aud Community Strength <span></span></th>
<th class="sortable" onclick="toggleSort('aud_confidence')">Aud Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('br_confidence')">Br Confidence <span></span></th>
<th class="sortable" onclick="toggleSort('act_status')">Act Status <span></span></th>
<th class="sortable" onclick="toggleSort('act_score')">Act Score <span></span></th>
<th class="sortable" onclick="toggleSort('act_consistency_score')">Act Consistency Score <span></span></th>
<th class="sortable" onclick="toggleSort('act_revived')">Act Revived <span></span></th>
<th class="sortable" onclick="toggleSort('act_last_upload_days')">Act Last Upload Days <span></span></th>
<th class="sortable" onclick="toggleSort('act_uploads_30d')">Act Uploads 30d <span></span></th>
<th class="sortable" onclick="toggleSort('act_uploads_90d')">Act Uploads 90d <span></span></th>
<th class="sortable" onclick="toggleSort('act_uploads_1y')">Act Uploads 1y <span></span></th>
<th class="sortable" onclick="toggleSort('act_avg_duration_min')">Act Avg Duration Min <span></span></th>
<th class="sortable" onclick="toggleSort('act_expected_gap_days')">Act Expected Gap Days <span></span></th>
<th class="sortable" onclick="toggleSort('act_actual_gap_days')">Act Actual Gap Days <span></span></th>
<th class="sortable" onclick="toggleSort('act_upload_frequency')">Act Upload Frequency <span></span></th>
<th class="sortable" onclick="toggleSort('act_frequency_ratio')">Act Frequency Ratio <span></span></th>
</tr>
</thead>
                            <tbody>
                                ${data.videos.map(v => `
                                    <tr>
                                        <td><span class="text-bold">${escapeHtml(v.title)}</span></td>
                                        <td class="cell-numeric">${(v.views || 0).toLocaleString()}</td>
                                        <td class="cell-numeric">${(v.likes || 0).toLocaleString()}</td>
                                        <td>${v.duration_minutes ? v.duration_minutes.toFixed(1) + ' min' : '-'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                ` : ''}
            `;

            modalBody.innerHTML = html;
        }

        function closeModal() {
            document.getElementById('channelModal').style.display = 'none';
        }

        document.getElementById('searchInput').addEventListener('input', (e) => {
            currentSearch = e.target.value;
            clearTimeout(window.searchTimeout);
            window.searchTimeout = setTimeout(() => loadChannels(1), 350);
        });

        document.getElementById('sortBy').addEventListener('change', (e) => {
            currentSort = e.target.value;
            loadChannels(1);
        });

        document.getElementById('perPage').addEventListener('change', (e) => {
            currentPerPage = parseInt(e.target.value);
            loadChannels(1);
        });

        window.onclick = function(event) {
            const modal = document.getElementById('channelModal');
            if (event.target === modal) {
                closeModal();
            }
        };

        function getActivityBadge(status) {
            if (!status) return '<span class="badge badge-default">-</span>';
            const classes = {
                'Excellent': 'badge-excellent',
                'Healthy': 'badge-healthy',
                'Active': 'badge-active',
                'Dormant': 'badge-dormant'
            };
            const className = classes[status] || 'badge-default';
            return `<span class="badge ${className}">${status}</span>`;
        }

        function formatDate(dateStr) {
            if (!dateStr) return '-';
            const date = new Date(dateStr);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }

        function escapeHtml(text) {
            if (!text) return '';
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return text.toString().replace(/[&<>"']/g, m => map[m]);
        }
    
        // --- Workspace Picker JS ---
        let activeWorkspace = 'default';
        let availableWorkspaces = ['default'];

        function toggleWorkspaceDropdown(e) {
            if (e) e.stopPropagation();
            const menu = document.getElementById('workspaceDropdownMenu');
            if (menu) {
                menu.classList.toggle('active');
            }
        }

        function renderWorkspaceList() {
            const listDiv = document.getElementById('workspaceList');
            if (!listDiv) return;
            listDiv.innerHTML = '';
            
            availableWorkspaces.forEach(ws => {
                const item = document.createElement('div');
                const isActive = ws === activeWorkspace;
                item.className = `ws-dropdown-item ${isActive ? 'active' : ''}`;
                item.onclick = (e) => {
                    e.stopPropagation();
                    selectWorkspace(ws);
                };
                item.innerHTML = `
                    <svg class="ws-item-check" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                    <span class="ws-item-name">${escapeHtml(ws)}</span>
                `;
                listDiv.appendChild(item);
            });
        }

        async function selectWorkspace(wsName) {
            try {
                const res = await fetch('/api/workspaces/active', {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: wsName})
                });
                if (res.ok) {
                    activeWorkspace = wsName;
                    const wsText = document.getElementById('currentWorkspaceText');
                    if (wsText) wsText.textContent = wsName;
                    
                    const menu = document.getElementById('workspaceDropdownMenu');
                    if (menu) menu.classList.remove('active');

                    renderWorkspaceList();
                    loadStats();
                    loadChannels(1);
                    showWinAlert(`Switched active workspace to "${wsName}".`, "Workspace Active", "info");
                } else {
                    const data = await res.json();
                    showWinAlert(data.error || "Failed to switch workspace.", "Workspace Error", "error");
                }
            } catch (e) {
                console.error("Error switching workspace:", e);
            }
        }

        async function createWorkspacePrompt() {
            const menu = document.getElementById('workspaceDropdownMenu');
            if (menu) menu.classList.remove('active');

            const wsName = await showWinPrompt("Enter name for new workspace (alphanumeric, no spaces):", "Create New Workspace");
            if (wsName && wsName.trim().length > 0) {
                const cleanName = wsName.trim();
                try {
                    const res = await fetch('/api/workspaces', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name: cleanName})
                    });
                    const data = await res.json();
                    if (res.ok) {
                        await loadWorkspaces();
                        loadStats();
                        loadChannels(1);
                        showWinAlert(`Workspace "${cleanName}" created successfully!`, "Workspace Created", "info");
                    } else {
                        showWinAlert(data.error || "Failed to create workspace.", "Workspace Error", "error");
                    }
                } catch (e) {
                    showWinAlert("Failed to create workspace: " + e.message, "Workspace Error", "error");
                }
            }
        }

        window.addEventListener('click', (e) => {
            const menu = document.getElementById('workspaceDropdownMenu');
            if (menu && !e.target.closest('.workspace-picker-wrapper')) {
                menu.classList.remove('active');
            }
        });

        // --- Scraper Operations JS ---
        let scrapeStatusTimer = null;
        let autorunStatusTimer = null;
        
        document.getElementById('scrapeMethod').addEventListener('change', (e) => {
            const isSearch = e.target.value === 'search';
            document.getElementById('searchOptions').style.display = isSearch ? 'flex' : 'none';
            document.getElementById('scrapeInputLabel').textContent = isSearch ? 'Keywords' : 'Channel Handle';
        });

        function toggleAiAnalyzers(enabled) {
            const group = document.getElementById('aiOptionsGroup');
            if (group) {
                group.style.opacity = enabled ? '1' : '0.5';
                group.style.pointerEvents = enabled ? 'auto' : 'none';
                const inputs = group.querySelectorAll('input');
                inputs.forEach(inp => {
                    if (inp.id !== 'scrapeDeep' || enabled) {
                        inp.disabled = !enabled;
                    }
                });
            }
            const chips = document.querySelectorAll('.ai-toggle');
            chips.forEach(chip => {
                chip.disabled = !enabled;
                chip.parentElement.style.opacity = enabled ? '1' : '0.5';
            });
        }

        async function startScrape() {
            const method = document.getElementById('scrapeMethod').value;
            const target = document.getElementById('scrapeTarget') ? document.getElementById('scrapeTarget').value : 'video';
            const query = document.getElementById('scrapeInput').value.trim();
            if (!query) {
                alert("Please enter a keyword or handle.");
                return;
            }
            const sort = document.getElementById('scrapeSort').value;
            const region = document.getElementById('scrapeRegion').value.trim();
            const language = document.getElementById('scrapeLanguage').value;
            const safeSearch = document.getElementById('scrapeSafeSearch').value;
            let pubAfter = document.getElementById('scrapePubAfter').value;
            let pubBefore = document.getElementById('scrapePubBefore').value;
            const maxResults = document.getElementById('scrapeMaxResults').value;
            const deepAnalysis = document.getElementById('scrapeDeep').checked;
            const deepLimit = document.getElementById('deepLimit').value;
            const runBenchmarking = document.getElementById('scrapeBench').checked;
            const competitorHandle = document.getElementById('benchHandle').value.trim();
            const topicId = document.getElementById('scrapeTopic').value;
            const scrapeDepth = document.getElementById('scrapeDepth').value;
            const useAi = document.getElementById('scrapeUseAI') ? document.getElementById('scrapeUseAI').checked : true;
            
            const aiToggles = {};
            document.querySelectorAll('.ai-toggle').forEach(cb => {
                aiToggles[cb.value] = cb.checked;
            });
            
            if (pubAfter) pubAfter = pubAfter + "T00:00:00Z";
            if (pubBefore) pubBefore = pubBefore + "T23:59:59Z";
            
            document.getElementById('btnStartScrape').disabled = true;
            document.getElementById('btnStartScrape').style.display = 'none';
            document.getElementById('btnStopScrape').disabled = false;
            document.getElementById('btnStopScrape').style.display = 'block';
            document.getElementById('scrapeLogBox').textContent = "Starting job...";
            
            try {
                const res = await fetch('/api/scrape/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ method, target, query, sort, region, language, safeSearch, pubAfter, pubBefore, maxResults: parseInt(maxResults), deepAnalysis, deepLimit: parseInt(deepLimit), runBenchmarking, competitorHandle, topicId, scrapeDepth: parseInt(scrapeDepth), useAi, aiToggles })
                });
                const data = await res.json();
                if (data.error) {
                    document.getElementById('scrapeLogBox').textContent += "\\nError: " + data.error;
                    document.getElementById('btnStartScrape').disabled = false;
                    document.getElementById('btnStartScrape').style.display = 'block';
                    document.getElementById('btnStopScrape').style.display = 'none';
                } else {
                    pollScrapeStatus();
                }
            } catch (e) {
                document.getElementById('scrapeLogBox').textContent += "\\nException: " + e;
                document.getElementById('btnStartScrape').disabled = false;
                document.getElementById('btnStartScrape').style.display = 'block';
                document.getElementById('btnStopScrape').style.display = 'none';
            }
        }
        
        async function stopScrape() {
            try {
                await fetch('/api/scrape/stop', {method: 'POST'});
                document.getElementById('btnStopScrape').disabled = true;
                document.getElementById('btnStopScrape').textContent = 'Stopping...';
            } catch (e) {
                console.error(e);
            }
        }
        
        async function pollScrapeStatus() {
            try {
                const res = await fetch('/api/scrape/status');
                const data = await res.json();
                          if (data.active) {
                    document.getElementById('scrapeLogBox').textContent = data.log.join('\\n');
                    scrapeStatusTimer = setTimeout(pollScrapeStatus, 1500);
                } else {
                    document.getElementById('scrapeLogBox').textContent = data.log.join('\\n') + "\\n[Job Finished]";
                    document.getElementById('btnStartScrape').disabled = false;
                    document.getElementById('btnStartScrape').style.display = 'block';
                    document.getElementById('btnStopScrape').disabled = true;
                    document.getElementById('btnStopScrape').style.display = 'none';
                    document.getElementById('btnStopScrape').textContent = 'Stop Job';
                    loadStats(); // refresh numbers
                }       
                const logBox = document.getElementById('scrapeLogBox');
                logBox.scrollTop = logBox.scrollHeight;
            } catch (e) {
                console.error(e);
            }
        }
        
        async function toggleAutorun() {
            const threshold = document.getElementById('autorunThreshold').value;
            try {
                const res = await fetch('/api/autorunner/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ threshold: parseInt(threshold) || 24 })
                });
                const data = await res.json();
                updateAutorunUI(data.active);
            } catch(e) {
                console.error(e);
            }
        }
        
        function updateAutorunUI(isActive) {
            const btn = document.getElementById('btnToggleAutorun');
            const statusDiv = document.getElementById('autorunStatus');
            const badge = document.getElementById('autorunStatusBadge');
            if (isActive) {
                btn.textContent = "Stop Autorunner Daemon";
                btn.className = "excel-btn";
                btn.style.color = "#d83b01";
                btn.style.borderColor = "#d83b01";
                statusDiv.textContent = "ACTIVE";
                if (badge) {
                    badge.className = "pulse-badge pulse-badge-active";
                }
                if (!autorunStatusTimer) pollAutorunStatus();
            } else {
                btn.textContent = "Start Autorunner Daemon";
                btn.className = "excel-btn excel-btn-primary";
                btn.style.color = "";
                btn.style.borderColor = "";
                statusDiv.textContent = "INACTIVE";
                if (badge) {
                    badge.className = "pulse-badge pulse-badge-inactive";
                }
                clearTimeout(autorunStatusTimer);
                autorunStatusTimer = null;
            }
        }
        
        async function pollAutorunStatus() {
            try {
                const res = await fetch('/api/autorunner/status');
                const data = await res.json();
                updateAutorunUI(data.active);
                if (data.active) {
                    document.getElementById('autorunLogBox').textContent = data.log.join('\\n');
                    const logBox = document.getElementById('autorunLogBox');
                    logBox.scrollTop = logBox.scrollHeight;
                    autorunStatusTimer = setTimeout(pollAutorunStatus, 2000);
                }
            } catch(e) {
                console.error(e);
            }
        }
        
        async function loadWorkspaces() {
            try {
                const res = await fetch('/api/workspaces');
                const data = await res.json();
                const activeRes = await fetch('/api/workspaces/active');
                const activeData = await activeRes.json();
                
                availableWorkspaces = data.workspaces || ['default'];
                activeWorkspace = activeData.active || 'default';
                
                const wsText = document.getElementById('currentWorkspaceText');
                if (wsText) wsText.textContent = activeWorkspace;
                
                renderWorkspaceList();
            } catch (e) {
                console.error("Failed to load workspaces", e);
            }
        }
        
        // Initial state check
        fetch('/api/autorunner/status').then(r=>r.json()).then(data => {
            updateAutorunUI(data.active);
            if (data.active) {
                document.getElementById('autorunThreshold').value = data.threshold;
            }
        }).catch(e => console.error(e));
        
        let activeTerminalSourceId = 'scrapeLogBox';

        function openFullscreenTerminal(logBoxId, titleText) {
            activeTerminalSourceId = logBoxId;
            const sourceEl = document.getElementById(logBoxId);
            const targetEl = document.getElementById('terminalModalLogContent');
            const titleEl = document.getElementById('terminalModalTitle');
            
            if (titleEl) titleEl.textContent = titleText || 'Telemetry Terminal Console';
            if (targetEl && sourceEl) {
                targetEl.textContent = sourceEl.textContent || 'No log output yet...';
            }
            
            const modal = document.getElementById('terminalModal');
            if (modal) {
                modal.classList.add('active');
                modal.style.display = 'flex';
            }
        }

        function closeFullscreenTerminal() {
            const modal = document.getElementById('terminalModal');
            if (modal) {
                modal.classList.remove('active');
                modal.style.display = 'none';
            }
        }

        function clearConsole(boxId) {
            const el = document.getElementById(boxId);
            if (el) el.textContent = 'Console cleared.';
        }

        function copyConsole(boxId) {
            const el = document.getElementById(boxId);
            if (el && el.textContent) {
                navigator.clipboard.writeText(el.textContent).then(() => {
                    showWinAlert("Log content copied to clipboard!", "Clipboard Copied", "info");
                });
            }
        }

        function clearModalTerminal() {
            const targetEl = document.getElementById('terminalModalLogContent');
            if (targetEl) targetEl.textContent = 'Console cleared.';
            clearConsole(activeTerminalSourceId);
        }

        function copyModalTerminal() {
            copyConsole(activeTerminalSourceId);
        }

        function applyPreset(presetType) {
            if (presetType === 'tech_saas') {
                document.getElementById('scrapeMethod').value = 'search';
                document.getElementById('scrapeInput').value = 'SaaS software tech review';
                document.getElementById('scrapeSort').value = 'popular';
                document.getElementById('scrapeRegion').value = 'usa';
                document.getElementById('scrapeTopic').value = '/m/07c1v';
                document.getElementById('scrapeMaxResults').value = '5';
            } else if (presetType === 'gaming_india') {
                document.getElementById('scrapeMethod').value = 'search';
                document.getElementById('scrapeInput').value = 'gaming live stream hindi';
                document.getElementById('scrapeSort').value = 'popular';
                document.getElementById('scrapeRegion').value = 'india';
                document.getElementById('scrapeTopic').value = '/m/0bzvm2';
                document.getElementById('scrapeMaxResults').value = '5';
            } else if (presetType === 'finance_investing') {
                document.getElementById('scrapeMethod').value = 'search';
                document.getElementById('scrapeInput').value = 'personal finance stock market investing';
                document.getElementById('scrapeSort').value = 'relevance';
                document.getElementById('scrapeTopic').value = '';
                document.getElementById('scrapeMaxResults').value = '5';
            } else if (presetType === 'sponsored_leads') {
                document.getElementById('scrapeMethod').value = 'search';
                document.getElementById('scrapeInput').value = 'tech review sponsor email';
                document.getElementById('scrapeSort').value = 'popular';
                document.getElementById('scrapeMaxResults').value = '5';
            }
            
            const event = new Event('change');
            document.getElementById('scrapeMethod').dispatchEvent(event);
            showWinAlert(`Preset applied! Scraper query set to "${document.getElementById('scrapeInput').value}".`, "Preset Loaded", "info");
        }

        // --- Enterprise Data Export & CRM Integration JS ---
        function triggerExport(format) {
            const params = new URLSearchParams(window.location.search);
            // Append current filter states
            if (currentSearch) params.set('search', currentSearch);
            if (currentSort) params.set('sort_by', currentSort);
            
            const minSubs = document.getElementById('filterMinSubs')?.value;
            const maxSubs = document.getElementById('filterMaxSubs')?.value;
            const minViews = document.getElementById('filterMinViews')?.value;
            const status = document.getElementById('filterStatus')?.value;
            const region = document.getElementById('filterRegion')?.value;
            const niche = document.getElementById('filterNiche')?.value;
            const quality = document.getElementById('filterQuality')?.value;
            const hasEmail = document.getElementById('filterHasEmail')?.checked ? '1' : '';
            const hasSponsor = document.getElementById('filterHasSponsorship')?.checked ? '1' : '';

            if (minSubs) params.set('min_subs', minSubs);
            if (maxSubs) params.set('max_subs', maxSubs);
            if (minViews) params.set('min_views', minViews);
            if (status) params.set('act_status', status);
            if (region) params.set('region', region);
            if (niche) params.set('niche', niche);
            if (quality) params.set('quality', quality);
            if (hasEmail) params.set('has_email', hasEmail);
            if (hasSponsor) params.set('has_sponsorship', hasSponsor);

            window.location.href = `/api/export/${format}?${params.toString()}`;
        }

        function openCRMModal() {
            const modal = document.getElementById('crmModal');
            if (modal) modal.classList.add('active');
        }

        function closeCRMModal() {
            const modal = document.getElementById('crmModal');
            if (modal) modal.classList.remove('active');
        }

        async function dispatchWebhook() {
            const url = document.getElementById('webhookUrlInput').value.trim();
            if (!url) {
                showWinAlert("Please enter a valid Webhook URL.", "Missing Webhook URL", "warning");
                return;
            }
            const statusBox = document.getElementById('crmStatusBox');
            statusBox.textContent = `Dispatching lead payload to ${url}...`;
            
            try {
                const params = new URLSearchParams(window.location.search);
                const res = await fetch(`/api/integrations/webhook?${params.toString()}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ webhook_url: url, limit: 50 })
                });
                const data = await res.json();
                if (res.ok) {
                    statusBox.textContent = `[SUCCESS] Dispatched ${data.dispatched_count} leads to Webhook! Response HTTP ${data.response_status}.`;
                    showWinAlert(`Successfully dispatched ${data.dispatched_count} leads to Webhook!`, "Webhook Dispatched", "info");
                } else {
                    statusBox.textContent = `[ERROR] ${data.error}`;
                    showWinAlert(data.error, "Webhook Error", "error");
                }
            } catch (e) {
                statusBox.textContent = `[EXCEPTION] ${e.message}`;
            }
        }

        async function syncHubSpot() {
            const apiKey = document.getElementById('hubspotApiKeyInput').value.trim();
            if (!apiKey) {
                showWinAlert("Please enter your HubSpot Access Token.", "Missing Access Token", "warning");
                return;
            }
            const statusBox = document.getElementById('crmStatusBox');
            statusBox.textContent = "Syncing lead records to HubSpot Contacts API...";
            
            try {
                const params = new URLSearchParams(window.location.search);
                const res = await fetch(`/api/integrations/hubspot?${params.toString()}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ api_key: apiKey, limit: 50 })
                });
                const data = await res.json();
                if (res.ok) {
                    statusBox.textContent = `[SUCCESS] Synced ${data.synced_count} leads to HubSpot Contacts catalog!`;
                    showWinAlert(`Successfully synced ${data.synced_count} leads to HubSpot CRM!`, "HubSpot Synced", "info");
                } else {
                    statusBox.textContent = `[ERROR] ${data.error}`;
                    showWinAlert(data.error, "HubSpot Error", "error");
                }
            } catch (e) {
                statusBox.textContent = `[EXCEPTION] ${e.message}`;
            }
        }

        // --- Visual Analytics & BI Dashboard JS ---
        let biCharts = {};

        async function loadAnalyticsData() {
            try {
                const res = await fetch('/api/analytics/summary');
                const data = await res.json();

                document.getElementById('biTotalChannels').textContent = (data.total_channels || 0).toLocaleString();
                document.getElementById('biAvgReadiness').textContent = (data.avg_readiness || 0) + ' / 100';
                document.getElementById('biSponsoredPct').textContent = (data.sponsored_pct || 0) + '%';
                document.getElementById('biEmailPct').textContent = (data.email_pct || 0) + '%';

                renderNicheChart(data.niches || {});
                renderQualityChart(data.qualities || {});
                renderOpportunityChart(data.matrix || []);
                renderRegionChart(data.regions || {});
            } catch (e) {
                console.error("Failed to load BI analytics", e);
            }
        }

        function renderNicheChart(nicheObj) {
            const ctx = document.getElementById('nicheChart')?.getContext('2d');
            if (!ctx) return;
            if (biCharts.niche) biCharts.niche.destroy();

            const labels = Object.keys(nicheObj);
            const values = Object.values(nicheObj);

            biCharts.niche = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels.length ? labels : ['Uncategorized'],
                    datasets: [{
                        data: values.length ? values : [1],
                        backgroundColor: ['#1056a0', '#0078d4', '#00b7c3', '#008272', '#107c41', '#b4009e', '#5c2d91', '#d83b01']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'right' } }
                }
            });
        }

        function renderQualityChart(qualObj) {
            const ctx = document.getElementById('qualityChart')?.getContext('2d');
            if (!ctx) return;
            if (biCharts.quality) biCharts.quality.destroy();

            const labels = Object.keys(qualObj);
            const values = Object.values(qualObj);

            biCharts.quality = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels.length ? labels : ['Unclassified'],
                    datasets: [{
                        label: 'Channel Count',
                        data: values.length ? values : [0],
                        backgroundColor: '#1056a0'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true } }
                }
            });
        }

        function renderOpportunityChart(matrixList) {
            const ctx = document.getElementById('opportunityChart')?.getContext('2d');
            if (!ctx) return;
            if (biCharts.opportunity) biCharts.opportunity.destroy();

            const points = matrixList.map(p => ({ x: p.x, y: p.y }));

            biCharts.opportunity = new Chart(ctx, {
                type: 'scatter',
                data: {
                    datasets: [{
                        label: 'Creator Leads',
                        data: points,
                        backgroundColor: '#d83b01'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { title: { display: true, text: 'Upload Activity Score' }, min: 0, max: 100 },
                        y: { title: { display: true, text: 'Sponsorship Readiness Score' }, min: 0, max: 100 }
                    }
                }
            });
        }

        function renderRegionChart(regionObj) {
            const ctx = document.getElementById('regionChart')?.getContext('2d');
            if (!ctx) return;
            if (biCharts.region) biCharts.region.destroy();

            const labels = Object.keys(regionObj);
            const values = Object.values(regionObj);

            biCharts.region = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels.length ? labels : ['Global'],
                    datasets: [{
                        label: 'Leads by Country',
                        data: values.length ? values : [0],
                        backgroundColor: '#107c41'
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } }
                }
            });
        }

        // --- API Key Pool Rotator JS ---
        function openKeyPoolModal() {
            const modal = document.getElementById('keyPoolModal');
            if (modal) {
                modal.classList.add('active');
                loadKeyPoolStatus();
            }
        }

        function closeKeyPoolModal() {
            const modal = document.getElementById('keyPoolModal');
            if (modal) modal.classList.remove('active');
        }

        async function loadKeyPoolStatus() {
            const listDiv = document.getElementById('keyPoolList');
            if (!listDiv) return;
            listDiv.innerHTML = '<div style="font-size: 11px; color: var(--text-secondary);">Querying key pool status...</div>';

            try {
                const res = await fetch('/api/keys/status');
                const data = await res.json();
                listDiv.innerHTML = '';

                if (!data.keys || data.keys.length === 0) {
                    listDiv.innerHTML = '<div style="font-size: 11px; color: var(--text-secondary);">No API keys registered in pool.</div>';
                    return;
                }

                data.keys.forEach((k, idx) => {
                    const isCurrent = data.active_info && data.active_info.key === k.key;
                    const maskedKey = k.key.substring(0, 8) + '...' + k.key.substring(k.key.length - 4);
                    const isExhausted = k.status === 'exhausted';

                    const item = document.createElement('div');
                    item.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; background: white; border: 1px solid var(--excel-border); border-radius: 3px; font-size: 11px;';
                    item.innerHTML = `
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-weight: 700; font-family: monospace;">Key #${idx + 1}: ${maskedKey}</span>
                            ${isCurrent ? '<span style="background: #e1dfdd; color: #1056a0; font-weight: 700; padding: 1px 5px; border-radius: 2px; font-size: 10px;">ACTIVE</span>' : ''}
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="color: var(--text-secondary);">Used: ${k.usage_count} times</span>
                            <span style="font-weight: 700; color: ${isExhausted ? '#d83b01' : '#107c41'};">${isExhausted ? 'EXHAUSTED' : 'HEALTHY'}</span>
                        </div>
                    `;
                    listDiv.appendChild(item);
                });
            } catch (e) {
                listDiv.innerHTML = `<div style="color: red; font-size: 11px;">Error loading key status: ${e.message}</div>`;
            }
        }

        async function addApiKeyToPool() {
            const input = document.getElementById('newApiKeyInput');
            const keyVal = input ? input.value.trim() : '';
            if (!keyVal) {
                showWinAlert("Please enter a valid YouTube API key string.", "Key Required", "warning");
                return;
            }

            try {
                const res = await fetch('/api/keys/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ key: keyVal })
                });
                const data = await res.json();
                if (res.ok) {
                    input.value = '';
                    loadKeyPoolStatus();
                    showWinAlert("YouTube API Key successfully registered to rotation pool!", "Key Registered", "info");
                } else {
                    showWinAlert(data.error || "Failed to register API key.", "Key Error", "error");
                }
            } catch (e) {
                showWinAlert("Failed to register key: " + e.message, "Key Error", "error");
            }
        }

        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeFullscreenTerminal();
                closeCRMModal();
                closeKeyPoolModal();
            }
        });

        loadWorkspaces();
    </script>
</body>
</html>
"""


# ==========================================
# BACKGROUND WORKERS
# ==========================================
def extract_channel_data_by_id(channel_id, scrape_depth=20):
    channel = channel_service.get_channel_by_id(channel_id)
    if not channel:
        return None, None, None, None
    uploads = video_service.get_uploads(channel["uploads_playlist"], max_results=scrape_depth)
    video_ids = [video["video_id"] for video in uploads]
    videos = stats_service.get_video_statistics(video_ids)
    category = CategoryExtractor.extract(videos)
    texts = [channel.get("description", "")]
    texts.extend(video.get("description", "") for video in videos)
    socials = SocialExtractor.extract(texts)
    return channel, videos, category, socials

def extract_channel_data(handle, scrape_depth=20):
    channel = channel_service.get_channel(handle)
    if not channel:
        return None, None, None, None
    uploads = video_service.get_uploads(channel["uploads_playlist"], max_results=scrape_depth)
    video_ids = [video["video_id"] for video in uploads]
    videos = stats_service.get_video_statistics(video_ids)
    category = CategoryExtractor.extract(videos)
    texts = [channel.get("description", "")]
    texts.extend(video.get("description", "") for video in videos)
    socials = SocialExtractor.extract(texts)
    return channel, videos, category, socials

def run_scrape_job(method, query, sort, region_code, language, safe_search, pub_after, pub_before, topic_id, max_results, scrape_depth, deep_analysis, deep_limit, ai_toggles, run_benchmarking, competitor_handle):
    global scrape_is_running, scrape_cancel_flag
    try:
        scrape_logs.append(f"Starting job: {method} for '{query}'...")
        
        run_id = None
        
        if method == "search":
            scrape_logs.append("Searching for channels...")
            order_map = {"popular": "viewCount", "new": "date", "relevance": "relevance"}
            order = order_map.get(sort, "relevance")
            
            final_channels = channel_service.search_channels(
                query, order, max_results, region_code,
                relevance_language=language or None,
                safe_search=safe_search or None,
                published_after=pub_after or None,
                published_before=pub_before or None,
                topic_id=topic_id or None
            )
            if not final_channels:
                scrape_logs.append("No channels found.")
                return
            
            if scrape_cancel_flag:
                scrape_logs.append("Job cancelled by user.")
                return
            
            run_id = insert_scrape_run(search_query=query, region_code=region_code, sort_order=order)
            scrape_logs.append(f"Found {len(final_channels)} channel(s). Processing all...")
            
            # Process ALL found channels, not just the first
            for ch_idx, ch_info in enumerate(final_channels):
                if scrape_cancel_flag:
                    scrape_logs.append("Job cancelled by user.")
                    return
                
                channel_handle = ch_info['handle']
                scrape_logs.append(f"\n[{ch_idx+1}/{len(final_channels)}] Processing: {ch_info['channel_name']} (@{channel_handle})")
                
                _process_single_channel(
                    channel_handle, run_id, scrape_depth, deep_analysis, deep_limit,
                    ai_toggles, run_benchmarking, competitor_handle
                )
        else:
            channel_handle = query
            run_id = insert_scrape_run()
            _process_single_channel(
                channel_handle, run_id, scrape_depth, deep_analysis, deep_limit,
                ai_toggles, run_benchmarking, competitor_handle
            )
            
        scrape_logs.append("Job completed successfully!")
    except Exception as e:
        scrape_logs.append(f"Error: {str(e)}")
        scrape_logs.append(traceback.format_exc())
    finally:
        scrape_is_running = False


def _process_single_channel(channel_handle, run_id, scrape_depth, deep_analysis, deep_limit, ai_toggles, run_benchmarking, competitor_handle):
    """Process a single channel: fetch data, run AI analyzers, save to DB."""
    global scrape_cancel_flag
    
    scrape_logs.append(f"Fetching data for {channel_handle}...")
    channel, videos, category, socials = extract_channel_data(channel_handle, scrape_depth=scrape_depth)
    
    if not channel:
        scrape_logs.append(f"Failed to fetch data for handle: {channel_handle}")
        return
        
    scrape_logs.append("Analyzing Creator Profile...")
    if scrape_cancel_flag:
        scrape_logs.append("Job cancelled by user.")
        return
    profile = CreatorProfileAnalyzer().analyze(channel, videos, category, socials)
    
    scrape_logs.append("Analyzing Audience...")
    top_audience_videos = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:5]
    audience_comments = []
    audience_transcripts = []
    for v in top_audience_videos:
        vid = v["video_id"]
        audience_comments.extend(CommentService.get_top_comments(vid, max_results=20))
        tr = TranscriptService.get_transcript(vid)
        if tr: audience_transcripts.append(tr)
        
    if scrape_cancel_flag:
        scrape_logs.append("Job cancelled by user.")
        return
    audience = AudienceAnalyzer().analyze(channel, videos, audience_comments, audience_transcripts)
    
    scrape_logs.append("Analyzing Brands, Quality, Sponsorship, Activity...")
    brands = BrandDetector().analyze(channel, videos, category, socials)
    quality = QualityAnalyzer().analyze(channel, videos, category, socials)
    sponsorship = SponsorshipAnalyzer().analyze(channel, videos, category, socials)
    activity = ActivityStatus.analyze(videos)
    
    scrape_logs.append("Saving channel data to DB...")
    ch_row_id = insert_channel(run_id, channel, category, profile, quality, sponsorship, audience, brands, activity)
    video_id_map = insert_videos(ch_row_id, videos)
    scrape_logs.append(f"Saved {len(videos)} videos.")
    
    if scrape_cancel_flag:
        scrape_logs.append("Job cancelled by user.")
        return
        
    if deep_analysis:
        scrape_logs.append(f"Running Deep Content Analysis on top {deep_limit} videos...")
        top_videos = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:deep_limit]
        for idx, v in enumerate(top_videos):
            if scrape_cancel_flag:
                scrape_logs.append("Job cancelled by user.")
                return
            vid_id = v["video_id"]
            scrape_logs.append(f"Deep analyzing video {idx+1}: {vid_id}...")
            
            tr = TranscriptService.get_transcript(vid_id)
            t_profile = TranscriptAnalyzer().analyze(tr) if tr else None
            
            comments = CommentService.get_top_comments(vid_id, max_results=20)
            s_profile = SentimentAnalyzer().analyze(comments) if comments else None
            
            thumb_path = ThumbnailService.download_thumbnail(vid_id)
            thumb_profile = None
            if thumb_path:
                try:
                    thumb_profile = ThumbnailAnalyzer().analyze(thumb_path)
                except Exception as e:
                    scrape_logs.append(f"Thumbnail error: {e}")
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                    
            if t_profile or s_profile or thumb_profile:
                vid_row = video_id_map.get(vid_id)
                if vid_row:
                    insert_video_deep_analysis(vid_row, t_profile, s_profile, thumb_profile)
                    
    
    if run_benchmarking and competitor_handle:
        if scrape_cancel_flag:
            scrape_logs.append("Job cancelled by user.")
            return
        scrape_logs.append(f"Running Benchmarking vs {competitor_handle}...")
        c_channel, c_videos, c_category, c_socials = extract_channel_data(competitor_handle)
        if not c_channel:
            scrape_logs.append(f"Could not fetch competitor {competitor_handle}")
        else:
            scrape_logs.append("Analyzing competitor data and generating report...")
            ctx_a = CreatorContextBuilder.build(channel, videos, category, socials)
            ctx_b = CreatorContextBuilder.build(c_channel, c_videos, c_category, c_socials)
            activity_a = ActivityStatus.analyze(videos)
            activity_b = ActivityStatus.analyze(c_videos)
            
            from youtube_lead_generator.ai.analyzers.benchmark_analyzer import Benchmarker
            from youtube_lead_generator.core.database import insert_benchmark
            benchmark_report = Benchmarker().analyze(ctx_a, ctx_b, activity_a, activity_b)
            insert_benchmark(run_id, ch_row_id, competitor_handle, benchmark_report)
            scrape_logs.append("Benchmark saved.")



def autorunner_loop():
    global autorunner_active
    while autorunner_active:
        conn = None
        try:
            conn = get_db_connection()
            if table_exists(conn, "channels"):
                # Get distinct channels
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT channel_id, channel_name FROM channels")
                rows = cursor.fetchall()
                conn.close()
                conn = None
                
                for row in rows:
                    if not autorunner_active:
                        break
                    ch_id = row['channel_id']
                    ch_name = row['channel_name']
                    
                    if should_rescrape(ch_id, autorunner_threshold):
                        autorunner_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Rescraping {ch_name} (Threshold exceeded)")
                        # Trigger scrape synchronously in this thread
                        run_id = insert_scrape_run()
                        ch, vids, cat, soc = extract_channel_data_by_id(ch_id, scrape_depth=20)
                        if ch:
                            profile = CreatorProfileAnalyzer().analyze(ch, vids, cat, soc)
                            audience = AudienceAnalyzer().analyze(ch, vids, [], []) # skip deep for speed
                            brands = BrandDetector().analyze(ch, vids, cat, soc)
                            quality = QualityAnalyzer().analyze(ch, vids, cat, soc)
                            sponsorship = SponsorshipAnalyzer().analyze(ch, vids, cat, soc)
                            activity = ActivityStatus.analyze(vids)
                            ch_row_id = insert_channel(run_id, ch, cat, profile, quality, sponsorship, audience, brands, activity)
                            insert_videos(ch_row_id, vids)
                            autorunner_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] Scraped {ch_name} successfully.")
                    else:
                        pass # Up to date
                
            # Sleep in chunks to allow fast stopping
            for _ in range(60):
                if not autorunner_active: break
                time.sleep(1)
        except Exception as e:
            autorunner_logs.append(f"Error in autorunner: {str(e)}")
            time.sleep(10)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


# ==========================================
# FLASK CORE ROUTING ENGINE & APIS
# ==========================================

@app.route('/')
def index():
    """Serves the main office-blue dashboard spreadsheet interface."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/analysis/<int:channel_id>')
def analysis_dashboard(channel_id):
    return render_template('analysis.html', channel_id=channel_id)

@app.route('/api/stats')
def get_stats():
    """Calculates summary KPIs across scrap run logs and entities."""
    try:
        conn = get_db_connection()
        
        # Safe detection mapping for various historical database configurations
        channels_table = "channels" if table_exists(conn, "channels") else None
        runs_table = "scrape_runs" if table_exists(conn, "scrape_runs") else None
        videos_table = "videos" if table_exists(conn, "videos") else None

        stats = {
            'total_channels': 0,
            'total_runs': 0,
            'total_videos': 0,
            'latest_scrape': None
        }

        if channels_table:
            # Handle potential variation in PK/identifier names
            cols = get_table_columns(conn, "channels")
            id_col = "id" if "id" in cols else ("channel_id" if "channel_id" in cols else "*")
            stats['total_channels'] = conn.execute(f"SELECT COUNT(DISTINCT {id_col}) FROM channels").fetchone()[0]
            
            # Use scraped_at as fallback if scrape_runs table is missing
            if "scraped_at" in cols:
                latest = conn.execute("SELECT MAX(scraped_at) FROM channels").fetchone()[0]
                stats['latest_scrape'] = latest

        if runs_table:
            stats['total_runs'] = conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0]
            latest_run = conn.execute("SELECT scraped_at FROM scrape_runs ORDER BY scraped_at DESC LIMIT 1").fetchone()
            if latest_run:
                stats['latest_scrape'] = latest_run[0]

        if videos_table:
            stats['total_videos'] = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

        conn.close()
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': f"Failed to compute statistics: {str(e)}"}), 500


@app.route('/api/channels')
def get_channels():
    """
    Returns search-filtered, sorted, and paginated channel records.
    Adapts dynamically to column aliases during execution.
    """
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        search = request.args.get('search', '').strip()
        sort_by = request.args.get('sort_by', 'scraped_at')
        order = request.args.get('order', 'DESC').upper()
        
        # Advanced Filters
        min_subs = request.args.get('min_subs', '').strip()
        max_subs = request.args.get('max_subs', '').strip()
        min_views = request.args.get('min_views', '').strip()
        max_views = request.args.get('max_views', '').strip()
        act_status = request.args.get('act_status', '').strip()
        region = request.args.get('region', '').strip()
        niche = request.args.get('niche', '').strip()
        quality = request.args.get('quality', '').strip()
        has_email = request.args.get('has_email', '').strip()
        has_sponsorship = request.args.get('has_sponsorship', '').strip()

        if order not in ('ASC', 'DESC'):
            order = 'DESC'

        conn = get_db_connection()
        
        if not table_exists(conn, "channels"):
            return jsonify({'channels': [], 'total': 0, 'page': 1, 'total_pages': 0})

        cols = get_table_columns(conn, "channels")
        
        # Defensive property mapping fallback rules (resolving naming variations)
        id_col = "id" if "id" in cols else "channel_id"
        niche_col = "cp_primary_niche" if "cp_primary_niche" in cols else ("niche" if "niche" in cols else None)
        sub_col = "subscriber_count" if "subscriber_count" in cols else ("subscribers" if "subscribers" in cols else None)
        views_col = "total_views" if "total_views" in cols else ("views" if "views" in cols else None)
        vids_col = "total_videos" if "total_videos" in cols else ("videos" if "videos" in cols else None)
        status_col = "act_status" if "act_status" in cols else ("activity" if "activity" in cols else None)
        qual_col = "q_production_quality" if "q_production_quality" in cols else ("quality" if "quality" in cols else None)
        time_col = "scraped_at" if "scraped_at" in cols else "id"

        # Validate sort column request against available table catalog
        sort_mapping = {
            'scraped_at': time_col,
            'subscriber_count': sub_col or id_col,
            'total_views': views_col or id_col,
            'total_videos': vids_col or id_col,
            'channel_name': 'channel_name',
            'act_score': 'act_score' if 'act_score' in cols else id_col,
            'act_last_upload_days': 'act_last_upload_days' if 'act_last_upload_days' in cols else id_col,
            'q_production_quality': qual_col or id_col,
            'sp_readiness': 'sp_readiness' if 'sp_readiness' in cols else id_col,
            'cp_primary_niche': niche_col or id_col,
            'id': id_col
        }
        active_sort = sort_mapping.get(sort_by, time_col)
        
        # Build flexible base Query
        query_parts = []
        params = {}

        if search:
            search_clause = ["channel_name LIKE :search"]
            if niche_col:
                search_clause.append(f"{niche_col} LIKE :search")
            if status_col:
                search_clause.append(f"{status_col} LIKE :search")
            if 'description' in cols:
                search_clause.append("description LIKE :search")
                
            query_parts.append(f"({' OR '.join(search_clause)})")
            params['search'] = f"%{search}%"

        # Apply advanced filters
        if min_subs and sub_col:
            query_parts.append(f"{sub_col} >= :min_subs")
            params['min_subs'] = int(min_subs)
        if max_subs and sub_col:
            query_parts.append(f"{sub_col} <= :max_subs")
            params['max_subs'] = int(max_subs)
        if min_views and views_col:
            query_parts.append(f"{views_col} >= :min_views")
            params['min_views'] = int(min_views)
        if max_views and views_col:
            query_parts.append(f"{views_col} <= :max_views")
            params['max_views'] = int(max_views)
        if act_status and status_col:
            query_parts.append(f"{status_col} = :act_status")
            params['act_status'] = act_status
        if region and 'country' in cols:
            query_parts.append("country = :region")
            params['region'] = region
        if niche and niche_col:
            query_parts.append(f"{niche_col} LIKE :niche")
            params['niche'] = f"%{niche}%"
        if quality and qual_col:
            query_parts.append(f"{qual_col} LIKE :quality")
            params['quality'] = f"%{quality}%"
        if has_email == '1' and 'email' in cols:
            query_parts.append("(email IS NOT NULL AND email != '')")
        if has_sponsorship == '1' and 'sp_has_sponsorships' in cols:
            query_parts.append("(sp_has_sponsorships = '1' OR sp_has_sponsorships = 1 OR sp_has_sponsorships LIKE '%Yes%' OR sp_has_sponsorships LIKE '%true%')")

        where_clause = f"WHERE {' AND '.join(query_parts)}" if query_parts else ""

        # Count total records for pagination ceiling calculations
        count_sql = f"SELECT COUNT(*) FROM channels {where_clause}"
        total_records = conn.execute(count_sql, params).fetchone()[0]

        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT *
            FROM channels
            {where_clause}
            ORDER BY {active_sort} {order}
            LIMIT :limit OFFSET :offset
        """
        
        params['limit'] = per_page
        params['offset'] = offset

        rows = conn.execute(data_sql, params).fetchall()
        channels = [dict(row) for row in rows]
        
        conn.close()

        return jsonify({
            'channels': channels,
            'total': total_records,
            'page': page,
            'total_pages': (total_records + per_page - 1) // per_page
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Query Error: {str(e)}"}), 500


@app.route('/api/channel/<int:channel_id>')
def get_channel_detail(channel_id):
    """
    Assembles complete sub-table segment graphs (Many-to-Many targets and videos)
    to feed the spreadsheet inspector dashboard.
    """
    try:
        conn = get_db_connection()
        
        if not table_exists(conn, "channels"):
            return jsonify({'error': 'Channels table missing'}), 404

        cols = get_table_columns(conn, "channels")
        id_col = "id" if "id" in cols else "channel_id"
        niche_col = "cp_primary_niche" if "cp_primary_niche" in cols else ("niche" if "niche" in cols else "NULL")
        sub_col = "subscriber_count" if "subscriber_count" in cols else ("subscribers" if "subscribers" in cols else "0")
        views_col = "total_views" if "total_views" in cols else ("views" if "views" in cols else "0")
        vids_col = "total_videos" if "total_videos" in cols else ("videos" if "videos" in cols else "0")
        status_col = "act_status" if "act_status" in cols else ("activity" if "activity" in cols else "NULL")
        score_col = "act_score" if "act_score" in cols else "NULL"
        qual_col = "q_production_quality" if "q_production_quality" in cols else ("quality" if "quality" in cols else "NULL")
        
        # Fetch Core Channel properties
        channel_sql = f"""
            SELECT 
                {id_col} AS id, channel_name, {niche_col} AS cp_primary_niche,
                {sub_col} AS subscriber_count, {views_col} AS total_views, {vids_col} AS total_videos,
                {status_col} AS act_status, {score_col} AS act_score, {qual_col} AS q_production_quality
            FROM channels
            WHERE {id_col} = ?
        """
        channel_row = conn.execute(channel_sql, (channel_id,)).fetchone()
        
        if not channel_row:
            conn.close()
            return jsonify({'error': 'Target record row index not found'}), 404
            
        channel_data = dict(channel_row)

        # Retrieve Child Video elements with fallback
        videos = []
        if table_exists(conn, "videos"):
            v_cols = get_table_columns(conn, "videos")
            duration_col = "duration_minutes" if "duration_minutes" in v_cols else "NULL"
            likes_col = "likes" if "likes" in v_cols else "0"
            
            video_sql = f"""
                SELECT v.id as video_id, v.title, v.views, v.{likes_col} AS likes, v.{duration_col} AS duration_minutes,
                       vda.id as da_id, vda.tr_has_sponsor_pitch, vda.tr_sponsor_style
                FROM videos v
                LEFT JOIN video_deep_analysis vda ON v.id = vda.video_id
                WHERE v.channel_id = ?
                ORDER BY v.views DESC
                LIMIT 5
            """
            video_rows = conn.execute(video_sql, (channel_id,)).fetchall()
            videos = []
            for r in video_rows:
                v = dict(r)
                da_id = v.get('da_id')
                if da_id:
                    v['topics'] = [tr[0] for tr in conn.execute("SELECT value FROM video_transcript_topics WHERE deep_analysis_id = ?", (da_id,)).fetchall()]
                    v['themes'] = [tr[0] for tr in conn.execute("SELECT value FROM video_sentiment_themes WHERE deep_analysis_id = ?", (da_id,)).fetchall()]
                    v['elements'] = [tr[0] for tr in conn.execute("SELECT value FROM video_thumbnail_elements WHERE deep_analysis_id = ?", (da_id,)).fetchall()]
                videos.append(v)

        # Meta relational query collectors (check both real and mock table names)
        content_styles = []
        if table_exists(conn, "channel_content_styles"):
            rows = conn.execute("SELECT value FROM channel_content_styles WHERE channel_id = ?", (channel_id,)).fetchall()
            content_styles = [r[0] for r in rows]
        elif table_exists(conn, "content_styles"):
            rows = conn.execute("SELECT style FROM content_styles WHERE channel_id = ?", (channel_id,)).fetchall()
            content_styles = [r[0] for r in rows]

        brands = []
        if table_exists(conn, "channel_brands"):
            rows = conn.execute("SELECT value FROM channel_brands WHERE channel_id = ?", (channel_id,)).fetchall()
            brands = [r[0] for r in rows]
        elif table_exists(conn, "brands"):
            rows = conn.execute("SELECT brand FROM brands WHERE channel_id = ?", (channel_id,)).fetchall()
            brands = [r[0] for r in rows]

        age_groups = []
        regions = []
        if table_exists(conn, "channel_audience_age_groups"):
            rows = conn.execute("SELECT value FROM channel_audience_age_groups WHERE channel_id = ?", (channel_id,)).fetchall()
            age_groups = [r[0] for r in rows]
        if table_exists(conn, "channel_audience_regions"):
            rows = conn.execute("SELECT value FROM channel_audience_regions WHERE channel_id = ?", (channel_id,)).fetchall()
            regions = [r[0] for r in rows]
        if not age_groups and not regions and table_exists(conn, "audience_demographics"):
            rows = conn.execute("SELECT category, value FROM audience_demographics WHERE channel_id = ?", (channel_id,)).fetchall()
            for r in rows:
                if r[0] == 'age':
                    age_groups.append(r[1])
                elif r[0] == 'region':
                    regions.append(r[1])

        conn.close()

        return jsonify({
            'channel': channel_data,
            'videos': videos,
            'content_styles': content_styles,
            'brands': brands,
            'audience_age_groups': age_groups,
            'audience_regions': regions
        })

    except Exception as e:
        return jsonify({'error': f"Detailed inspection failed: {str(e)}"}), 500


# ==========================================
# BOOT EXECUTION TARGET
# ==========================================

@app.route('/api/scrape/run', methods=['POST'])
def api_scrape_run():
    global scrape_is_running, scrape_cancel_flag
    with scrape_lock:
        if scrape_is_running:
            return jsonify({"error": "A job is already running."}), 400
        scrape_is_running = True
        scrape_cancel_flag = False
        
    data = request.json
    method = data.get('method', 'search')
    query = data.get('query', '')
    sort = data.get('sort', 'relevance')
    region = data.get('region', '')
    language = data.get('language', '')
    safe_search = data.get('safeSearch', 'moderate')
    pub_after = data.get('pubAfter', '')
    pub_before = data.get('pubBefore', '')
    max_results = data.get('maxResults', 1)
    deep_analysis = data.get('deepAnalysis', False)
    deep_limit = data.get('deepLimit', 3)
    run_benchmarking = data.get('runBenchmarking', False)
    competitor_handle = data.get('competitorHandle', '')
    topic_id = data.get('topicId', '')
    scrape_depth = data.get('scrapeDepth', 20)
    ai_toggles = data.get('aiToggles', {})
    
    # map region code
    region_code = None
    if region:
        region_code = COUNTRY_CODES.get(region.lower(), region.upper())
        if len(region_code) != 2: region_code = None

    scrape_logs.clear()
    
    t = threading.Thread(target=run_scrape_job, args=(method, query, sort, region_code, language, safe_search, pub_after, pub_before, topic_id, max_results, scrape_depth, deep_analysis, deep_limit, ai_toggles, run_benchmarking, competitor_handle))
    t.daemon = True
    t.start()
    
    return jsonify({"status": "started"})

@app.route('/api/scrape/stop', methods=['POST'])
def api_scrape_stop():
    global scrape_cancel_flag
    scrape_cancel_flag = True
    return jsonify({"status": "cancelling"})

@app.route('/api/scrape/status')
def api_scrape_status():
    return jsonify({
        "active": scrape_is_running,
        "log": list(scrape_logs)
    })

@app.route('/api/autorunner/toggle', methods=['POST'])
def api_autorunner_toggle():
    global autorunner_active, autorunner_thread, autorunner_threshold
    
    if autorunner_active:
        autorunner_active = False
        autorunner_logs.append("Autorunner stopped.")
    else:
        threshold = request.json.get('threshold', 24)
        autorunner_threshold = threshold
        autorunner_active = True
        autorunner_logs.clear()
        autorunner_logs.append(f"Autorunner started with {threshold}h threshold.")
        autorunner_thread = threading.Thread(target=autorunner_loop)
        autorunner_thread.daemon = True
        autorunner_thread.start()
        
    return jsonify({"active": autorunner_active, "threshold": autorunner_threshold})

@app.route('/api/autorunner/status')
def api_autorunner_status():
    return jsonify({
        "active": autorunner_active,
        "threshold": autorunner_threshold,
        "log": list(autorunner_logs)
    })

@app.route('/api/workspaces', methods=['GET'])
def api_get_workspaces():
    return jsonify({"workspaces": WorkspaceManager.list_workspaces()})

@app.route('/api/workspaces', methods=['POST'])
def api_create_workspace():
    name = request.json.get('name')
    if not name:
        return jsonify({"error": "Name required"}), 400
    try:
        WorkspaceManager.create_workspace(name)
        init_db() # initializes schema for the newly active workspace
        return jsonify({"status": "success", "active": WorkspaceManager.get_active()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/workspaces/active', methods=['GET'])
def api_get_active_workspace():
    return jsonify({"active": WorkspaceManager.get_active()})

@app.route('/api/workspaces/active', methods=['PUT'])
def api_set_active_workspace():
    name = request.json.get('name')
    if not name:
        return jsonify({"error": "Name required"}), 400
    try:
        WorkspaceManager.set_active(name)
        return jsonify({"status": "success", "active": WorkspaceManager.get_active()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

# ==========================================
# ENTERPRISE EXPORT & CRM INTEGRATION ENGINE
# ==========================================

def fetch_filtered_channels(request_args, limit_override=None):
    """Helper function to fetch filtered channels for grid view, export, or integration sync."""
    search = request_args.get('search', '').strip()
    sort_by = request_args.get('sort_by', 'scraped_at')
    order = request_args.get('order', 'DESC').upper()
    
    min_subs = request_args.get('min_subs', '').strip()
    max_subs = request_args.get('max_subs', '').strip()
    min_views = request_args.get('min_views', '').strip()
    max_views = request_args.get('max_views', '').strip()
    act_status = request_args.get('act_status', '').strip()
    region = request_args.get('region', '').strip()
    niche = request_args.get('niche', '').strip()
    quality = request_args.get('quality', '').strip()
    has_email = request_args.get('has_email', '').strip()
    has_sponsorship = request_args.get('has_sponsorship', '').strip()

    if order not in ('ASC', 'DESC'):
        order = 'DESC'

    conn = get_db_connection()
    if not table_exists(conn, "channels"):
        conn.close()
        return [], 0

    cols = get_table_columns(conn, "channels")
    id_col = "id" if "id" in cols else "channel_id"
    niche_col = "cp_primary_niche" if "cp_primary_niche" in cols else ("niche" if "niche" in cols else None)
    sub_col = "subscriber_count" if "subscriber_count" in cols else ("subscribers" if "subscribers" in cols else None)
    views_col = "total_views" if "total_views" in cols else ("views" if "views" in cols else None)
    vids_col = "total_videos" if "total_videos" in cols else ("videos" if "videos" in cols else None)
    status_col = "act_status" if "act_status" in cols else ("activity" if "activity" in cols else None)
    qual_col = "q_production_quality" if "q_production_quality" in cols else ("quality" if "quality" in cols else None)
    time_col = "scraped_at" if "scraped_at" in cols else "id"

    sort_mapping = {
        'scraped_at': time_col,
        'subscriber_count': sub_col or id_col,
        'total_views': views_col or id_col,
        'total_videos': vids_col or id_col,
        'channel_name': 'channel_name',
        'act_score': 'act_score' if 'act_score' in cols else id_col,
        'act_last_upload_days': 'act_last_upload_days' if 'act_last_upload_days' in cols else id_col,
        'q_production_quality': qual_col or id_col,
        'sp_readiness': 'sp_readiness' if 'sp_readiness' in cols else id_col,
        'cp_primary_niche': niche_col or id_col,
        'id': id_col
    }
    active_sort = sort_mapping.get(sort_by, time_col)
    
    query_parts = []
    params = {}

    if search:
        search_clause = ["channel_name LIKE :search"]
        if niche_col: search_clause.append(f"{niche_col} LIKE :search")
        if status_col: search_clause.append(f"{status_col} LIKE :search")
        if 'description' in cols: search_clause.append("description LIKE :search")
        query_parts.append(f"({' OR '.join(search_clause)})")
        params['search'] = f"%{search}%"

    if min_subs and sub_col: query_parts.append(f"{sub_col} >= :min_subs"); params['min_subs'] = int(min_subs)
    if max_subs and sub_col: query_parts.append(f"{sub_col} <= :max_subs"); params['max_subs'] = int(max_subs)
    if min_views and views_col: query_parts.append(f"{views_col} >= :min_views"); params['min_views'] = int(min_views)
    if max_views and views_col: query_parts.append(f"{views_col} <= :max_views"); params['max_views'] = int(max_views)
    if act_status and status_col: query_parts.append(f"{status_col} = :act_status"); params['act_status'] = act_status
    if region and 'country' in cols: query_parts.append("country = :region"); params['region'] = region
    if niche and niche_col: query_parts.append(f"{niche_col} LIKE :niche"); params['niche'] = f"%{niche}%"
    if quality and qual_col: query_parts.append(f"{qual_col} LIKE :quality"); params['quality'] = f"%{quality}%"
    if has_email == '1' and 'email' in cols: query_parts.append("(email IS NOT NULL AND email != '')")
    if has_sponsorship == '1' and 'sp_has_sponsorships' in cols: query_parts.append("(sp_has_sponsorships = '1' OR sp_has_sponsorships = 1 OR sp_has_sponsorships LIKE '%Yes%' OR sp_has_sponsorships LIKE '%true%')")

    where_clause = f"WHERE {' AND '.join(query_parts)}" if query_parts else ""
    
    count_sql = f"SELECT COUNT(*) FROM channels {where_clause}"
    total_records = conn.execute(count_sql, params).fetchone()[0]

    limit = limit_override or int(request_args.get('per_page', 5000))
    page = int(request_args.get('page', 1))
    offset = (page - 1) * limit if limit_override is None else 0

    data_sql = f"""
        SELECT * FROM channels
        {where_clause}
        ORDER BY {active_sort} {order}
        LIMIT :limit OFFSET :offset
    """
    params['limit'] = limit
    params['offset'] = offset

    cursor = conn.execute(data_sql, params)
    channels = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return channels, total_records


@app.route('/api/export/csv')
def export_csv():
    """Generates and downloads a CSV export of filtered channel records."""
    import csv
    import io

    channels, _ = fetch_filtered_channels(request.args)
    if not channels:
        return jsonify({"error": "No channels match your export filters."}), 404

    fieldnames = list(channels[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(channels)

    filename = f"youtube_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route('/api/export/xlsx')
def export_xlsx():
    """Generates an enterprise-styled multi-sheet Excel (.xlsx) workbook."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    channels, _ = fetch_filtered_channels(request.args)
    if not channels:
        return jsonify({"error": "No channels match your export filters."}), 404

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "YouTube Lead Index"

    # Define Enterprise Excel Styling
    header_fill = PatternFill(start_color="1056A0", end_color="1056A0", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    headers = list(channels[0].keys())
    ws.append(headers)

    for col_idx, col_name in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, row_data in enumerate(channels, start=2):
        for col_idx, key in enumerate(headers, start=1):
            val = row_data.get(key)
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = data_font
            cell.border = thin_border
            if isinstance(val, (int, float)):
                cell.alignment = Alignment(horizontal="right", vertical="center")

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"youtube_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route('/api/integrations/webhook', methods=['POST'])
def api_webhook_dispatch():
    """Dispatches lead JSON array to an external Webhook (Zapier / Make / n8n / custom API)."""
    data = request.json or {}
    webhook_url = data.get('webhook_url', '').strip()
    if not webhook_url:
        return jsonify({"error": "Webhook URL is required."}), 400

    channels, total = fetch_filtered_channels(request.args, limit_override=data.get('limit', 50))
    if not channels:
        return jsonify({"error": "No leads match current filter criteria."}), 404

    payload = {
        "event": "lead_export_dispatch",
        "timestamp": datetime.now().isoformat(),
        "lead_count": len(channels),
        "workspace": WorkspaceManager.get_active(),
        "leads": channels
    }

    try:
        import requests
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return jsonify({
            "status": "success",
            "dispatched_count": len(channels),
            "response_status": resp.status_code
        })
    except Exception as e:
        return jsonify({"error": f"Webhook dispatch failed: {str(e)}"}), 500


@app.route('/api/integrations/hubspot', methods=['POST'])
def api_hubspot_sync():
    """Syncs lead records to HubSpot Contacts API."""
    data = request.json or {}
    api_key = data.get('api_key', '').strip()
    if not api_key:
        return jsonify({"error": "HubSpot Access Token / API Key is required."}), 400

    channels, total = fetch_filtered_channels(request.args, limit_override=data.get('limit', 50))
    if not channels:
        return jsonify({"error": "No leads match current filter criteria."}), 404

    contacts = []
    for ch in channels:
        email = ch.get('email') or ch.get('sp_business_email') or f"contact_{ch.get('channel_id')}@youtube.lead"
        contacts.append({
            "properties": {
                "email": email,
                "firstname": ch.get('channel_name', ''),
                "website": f"https://youtube.com/channel/{ch.get('channel_id', '')}",
                "company": ch.get('channel_name', ''),
                "num_subscribers": str(ch.get('subscriber_count', 0)),
                "total_views": str(ch.get('total_views', 0)),
                "niche": ch.get('cp_primary_niche', '')
            }
        })

    try:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        resp = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts/batch/create",
            json={"inputs": contacts},
            headers=headers,
            timeout=15
        )
        if resp.status_code in (200, 201):
            return jsonify({"status": "success", "synced_count": len(contacts)})
        else:
            return jsonify({"error": f"HubSpot API error ({resp.status_code}): {resp.text}"}), 400
    except Exception as e:
        return jsonify({"error": f"HubSpot sync failed: {str(e)}"}), 500


@app.route('/api/analytics/summary')
def api_analytics_summary():
    """Computes aggregated BI visual metrics across indexed channels."""
    conn = get_db_connection()
    if not table_exists(conn, "channels"):
        conn.close()
        return jsonify({
            "total_channels": 0, "avg_readiness": 0, "sponsored_pct": 0, "email_pct": 0,
            "niches": {}, "qualities": {}, "regions": {}, "matrix": []
        })

    cols = get_table_columns(conn, "channels")
    niche_col = "cp_primary_niche" if "cp_primary_niche" in cols else ("niche" if "niche" in cols else None)
    qual_col = "q_production_quality" if "q_production_quality" in cols else ("quality" if "quality" in cols else None)
    
    total_channels = conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]

    avg_readiness = 0
    if "sp_readiness" in cols and total_channels > 0:
        res = conn.execute("SELECT AVG(CAST(sp_readiness AS FLOAT)) FROM channels WHERE sp_readiness IS NOT NULL AND sp_readiness != ''").fetchone()[0]
        avg_readiness = round(res or 0, 1)

    sponsored_pct = 0
    if "sp_has_sponsorships" in cols and total_channels > 0:
        count = conn.execute("SELECT COUNT(*) FROM channels WHERE sp_has_sponsorships = '1' OR sp_has_sponsorships = 1 OR sp_has_sponsorships LIKE '%Yes%'").fetchone()[0]
        sponsored_pct = round((count / total_channels * 100), 1)

    email_pct = 0
    if ("email" in cols or "sp_business_email" in cols) and total_channels > 0:
        email_col = "sp_business_email" if "sp_business_email" in cols else "email"
        count = conn.execute(f"SELECT COUNT(*) FROM channels WHERE {email_col} IS NOT NULL AND {email_col} != ''").fetchone()[0]
        email_pct = round((count / total_channels * 100), 1)

    niche_counts = {}
    if niche_col:
        rows = conn.execute(f"SELECT {niche_col}, COUNT(*) FROM channels WHERE {niche_col} IS NOT NULL AND {niche_col} != '' GROUP BY {niche_col} ORDER BY COUNT(*) DESC LIMIT 8").fetchall()
        niche_counts = {r[0]: r[1] for r in rows}

    qual_counts = {}
    if qual_col:
        rows = conn.execute(f"SELECT {qual_col}, COUNT(*) FROM channels WHERE {qual_col} IS NOT NULL AND {qual_col} != '' GROUP BY {qual_col}").fetchall()
        qual_counts = {r[0]: r[1] for r in rows}

    region_counts = {}
    if "country" in cols:
        rows = conn.execute("SELECT country, COUNT(*) FROM channels WHERE country IS NOT NULL AND country != '' GROUP BY country ORDER BY COUNT(*) DESC LIMIT 7").fetchall()
        region_counts = {r[0]: r[1] for r in rows}

    matrix_data = []
    if "act_score" in cols and "sp_readiness" in cols:
        rows = conn.execute("SELECT channel_name, CAST(act_score AS FLOAT), CAST(sp_readiness AS FLOAT) FROM channels WHERE act_score IS NOT NULL AND sp_readiness IS NOT NULL LIMIT 50").fetchall()
        matrix_data = [{"channel": r[0], "x": r[1] or 0, "y": r[2] or 0} for r in rows if r[1] is not None and r[2] is not None]

    conn.close()

    return jsonify({
        "total_channels": total_channels,
        "avg_readiness": avg_readiness,
        "sponsored_pct": sponsored_pct,
        "email_pct": email_pct,
        "niches": niche_counts,
        "qualities": qual_counts,
        "regions": region_counts,
        "matrix": matrix_data
    })

# ==========================================
# API KEY POOL & QUEUE INFRASTRUCTURE APIS
# ==========================================

@app.route('/api/keys/status')
def api_keys_status():
    """Returns real-time status of all registered YouTube API Keys in the pool."""
    from youtube_lead_generator.core.youtube_client import APIKeyPoolManager
    return jsonify({
        "keys": APIKeyPoolManager.get_pool_status(),
        "active_info": APIKeyPoolManager.get_active_key_info()
    })

@app.route('/api/keys/add', methods=['POST'])
def api_keys_add():
    """Dynamically adds a new YouTube API Key to the rotation pool."""
    from youtube_lead_generator.core.youtube_client import APIKeyPoolManager
    data = request.json or {}
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"error": "API Key is required."}), 400
    
    success = APIKeyPoolManager.add_key(key)
    if success:
        return jsonify({"status": "success", "message": "API key registered to rotation pool."})
    else:
        return jsonify({"error": "API key already exists in pool or is invalid."}), 400

@app.route('/api/queue/list')
def api_queue_list():
    """Returns extraction job queue items."""
    from youtube_lead_generator.services import ExtractionJobQueue
    return jsonify({"jobs": ExtractionJobQueue.list_jobs()})

@app.route('/api/queue/clear', methods=['POST'])
def api_queue_clear():
    """Clears completed extraction jobs."""
    from youtube_lead_generator.services import ExtractionJobQueue
    ExtractionJobQueue.clear_completed()
    return jsonify({"status": "cleared"})


# ==========================================
# ENTERPRISE SECURITY, RBAC & AUDIT LOG APIS
# ==========================================

def get_current_user():
    """Retrieves current session user or default Admin profile."""
    return session.get('user', {
        "username": "admin",
        "name": "System Administrator",
        "role": "Admin"
    })

def require_role(required_role):
    """Decorator enforcing Role-Based Access Control (RBAC)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not AuthService.has_permission(user.get("role", "Viewer"), required_role):
                AuditLogger.log(user.get("username"), "PERMISSION_DENIED", f"Attempted action requiring '{required_role}' role")
                return jsonify({"error": f"Access Denied: Action requires '{required_role}' role."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """Authenticates enterprise user credentials."""
    data = request.json or {}
    username = data.get("username", "")
    password = data.get("password", "")

    user = AuthService.authenticate(username, password)
    if user:
        session['user'] = user
        AuditLogger.log(user["username"], "USER_LOGIN_SUCCESS", f"Role: {user['role']}")
        return jsonify({"status": "success", "user": user})
    else:
        AuditLogger.log(username, "USER_LOGIN_FAILED", "Invalid credentials")
        return jsonify({"error": "Invalid username or password."}), 401


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    """Logs out current user session."""
    user = get_current_user()
    AuditLogger.log(user.get("username"), "USER_LOGOUT")
    session.pop('user', None)
    return jsonify({"status": "success"})


@app.route('/api/auth/me')
def api_auth_me():
    """Returns currently authenticated user metadata."""
    return jsonify({"user": get_current_user(), "available_users": AuthService.get_users_list()})


@app.route('/api/audit/logs')
def api_audit_logs():
    """Returns system audit trail logs."""
    limit = int(request.args.get("limit", 100))
    return jsonify({"logs": AuditLogger.get_logs(limit)})


if __name__ == '__main__':
    # Execute defensive DB configuration check on launch
    db_path = WorkspaceManager.get_db_path()
    if not db_path.exists() or os.path.getsize(db_path) == 0:
        init_mock_db()

    print("\n" + "="*60)
    print(" YouTube Scraper Workbook Console Active")
    print("="*60)
    print("\n Workspace Link: http://localhost:5000")
    print(" To terminate background thread: Press Ctrl+C\n")
    
    app.run(debug=False, host='127.0.0.1', port=5000)
