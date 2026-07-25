# AGENTS.md — YouTube Lead Generator & Intelligence Platform

Welcome to the **YouTube Lead Generator & Intelligence Platform** codebase. This document defines the project architecture, database schemas, AI analysis pipelines, frontend UI components, workspace management, and development guidelines for all AI agents and human collaborators working on this repository.

---

## 1. Project Overview

The **YouTube Lead Generator** is an enterprise-grade channel scraper, lead qualification, and AI-powered creator telemetry system. It enables automated discovery, deep analysis, and tracking of YouTube channels for sponsorship outreach, influencer marketing, brand monitoring, and competitive research.

### Key Highlights
- **Dual Execution Engine**:
  - **Executive Web Workbook Console (`web.py`)**: A modern, office-blue spreadsheet interface styled after Microsoft Excel with live grid pagination, column visibility pickers, custom floating workspace popovers, 2-line filter toolbars, and high-tech developer terminal consoles.
  - **Background Autorunner Daemon (`auto_run.py` / `main.py`)**: Automated background monitoring daemon that rescrapes out-of-date channel entries based on configurable freshness thresholds.
- **AI Pipeline Integration**:
  - Powered by **Google Gemini 2.0 Flash Lite** (`gemini-2.0-flash-lite`) via structured Pydantic schemas and custom context builders.
- **Multi-Tenant Workspace Isolation**:
  - Managed by `WorkspaceManager` (`workspace_manager.py`), storing isolated SQLite databases for different lead categories (`workspaces/<workspace_name>.db`).

---

## 2. Architecture & Directory Structure

```
d:\Projects\Youtube-Lead-Generator\
├── src/                                # Primary Application Package Root (PyPA Standard)
│   └── youtube_lead_generator/         # Root Package Namespace
│       ├── core/                       # Core Infrastructure & Workspace Subsystem
│       │   ├── config.py               # Global Configuration & API Key Registries
│       │   ├── auto_config.py          # Scraper Daemon Config
│       │   ├── database.py             # SQLite Schema Definition, Migrations, & CRUD Helpers
│       │   ├── workspace_manager.py    # Workspace Switcher & Multi-DB Isolation Manager
│       │   └── youtube_client.py       # YouTube Data API v3 Client Setup
│       ├── services/                   # Business Logic & Data Extraction Services
│       │   ├── youtube/                # YouTube Data API Fetchers (Channel, Video, Comments)
│       │   ├── extractors/             # Data Parsers (Category, Socials, Transcripts, Thumbnails)
│       │   ├── analytics/              # Activity Scoring & Telemetry Analytics
│       │   └── system/                 # Auth, Audit Logger, & Job Queue
│       ├── ai/                         # AI Pipeline Subsystem (Gemini 2.0 Flash Lite)
│       │   ├── base_ai_service.py      # Base Gemini Client Infrastructure
│       │   ├── analyzers/              # Specialized Analyzer Modules
│       │   ├── builders/               # Structured Context Builders
│       │   ├── clients/                # Gemini Client Infrastructure
│       │   ├── schemas/                # Pydantic Output Schemas
│       │   └── prompts/                # Prompt Templates
│       └── web/                        # Presentation Layer
│           ├── app.py                  # Flask Application Factory & Controllers
│           └── templates/              # Jinja2 HTML Templates
├── cli/                                # Command-Line Executable Interfaces
│   ├── main.py                         # Standalone Scraper CLI Execution
│   └── auto_run.py                     # Continuous Scraping Daemon Execution
├── workspaces/                         # Isolated Workspace SQLite Files (.db)
├── web.py                              # Top-Level Web Server Launcher (`python web.py`)
├── main.py                             # Top-Level CLI Launcher (`python main.py`)
├── auto_run.py                         # Top-Level Daemon Launcher (`python auto_run.py`)
└── requirements.txt                    # Python Dependencies
```

---

## 3. Database Architecture & Schema

The platform uses SQLite with `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL` for maximum concurrency and data safety. Database schema initialization is handled by `database.py:init_db()`.

### Primary Database Tables (`workspaces/<name>.db`)

| Table Name | Description | Key Columns |
| :--- | :--- | :--- |
| **`scrape_runs`** | Log of scraper execution cycles | `id`, `scraped_at`, `search_query`, `region_code`, `sort_order` |
| **`channels`** | Core channel index & metadata | `id`, `channel_id`, `channel_name`, `handle`, `subscriber_count`, `total_views`, `total_videos`, `country`, `act_status`, `act_score`, `cp_primary_niche`, `scraped_at` |
| **`videos`** | Scraped channel upload videos | `id`, `channel_id`, `video_id`, `title`, `views`, `likes`, `published_at`, `duration_minutes` |
| **`content_styles`** | Content format classifications | `id`, `channel_id`, `style` |
| **`brands`** | Detected sponsor/brand mentions | `id`, `channel_id`, `brand` |
| **`audience_demographics`** | Audience age/gender/region splits | `id`, `channel_id`, `category`, `value` |
| **`creator_profiles`** | AI-generated creator breakdown | `id`, `channel_id`, `summary`, `strengths`, `target_audience` |
| **`sponsorship_readiness`** | Sponsorship qualification score | `id`, `channel_id`, `readiness_score`, `has_sponsorships`, `business_email` |
| **`quality_scores`** | Channel content quality evaluation | `id`, `channel_id`, `production_quality`, `consistency`, `originality` |
| **`activity_metrics`** | Upload frequency & consistency metrics | `id`, `channel_id`, `last_upload_days`, `uploads_30d`, `uploads_90d`, `uploads_1y` |
| **`benchmarks`** | Competitor benchmarking comparisons | `id`, `run_id`, `channel_id`, `competitor_handle`, `report_json` |

---

## 4. Frontend & User Interface System

The web frontend (`web.py`) strictly adheres to an **Executive Microsoft Excel Theme Palette**:

### Core UI Components & Conventions
- **SVG Icons Only**: Emojis are strictly forbidden across buttons, checkboxes, dropdowns, and status badges. All UI controls use crisp vector SVG icons (`<svg class="excel-icon">`).
- **Theme-Matched Retro Office Dialogs**: Native browser `alert()` and `prompt()` functions are replaced with retro Office/Windows dialog modals (`showWinAlert`, `showWinPrompt`) rendered with proper title bars, action buttons, and icons (`info`, `warning`, `error`, `question`).
- **Workspace Selector Component**:
  - A custom translucent pill badge in the top ribbon containing a database vector icon, muted `"Workspace:"` label, bold active workspace name, and custom dropdown chevron.
  - Toggles a custom floating card popover menu (`#workspaceDropdownMenu`) showing active workspace checkmark (`✓`) and a `+ Create New Workspace...` action button.
- **Fixed Screen Boundaries & Pinned Footer**:
  - The viewport is constrained with `body { height: 100vh; overflow: hidden; }`.
  - Grid content scrolls inside `.grid-container`, while `.sheet-footer` (showing page status and pagination controls) remains pinned at the very bottom of the screen regardless of table row count.
- **2-Line Filter & Sorting Toolbar**:
  - **Row 1 (Sorting & Pagination)**: Search query box, Sort By dropdown (`scraped_at`, `subscriber_count`, `total_views`, `act_score`, `q_production_quality`, `sp_readiness`, etc.), Order (`ASC`/`DESC`), Limit per page, Reset Filters button, and Column Visibility Picker (`#columnFilterDropdown`).
  - **Row 2 (Advanced Entity Filters)**: Numeric ranges (`Min/Max Subs`, `Min Views`), Activity Status, Region, Niche, Content Quality, `Has Email` checkbox, and `Sponsored` checkbox.
- **Column Visibility Picker Filter**:
  - Dropdown menu allowing users to dynamically toggle visibility of all 50+ data columns, with quick presets: *Select All*, *Deselect All*, and *Essential View*.
- **Scraper Operations Dashboard**:
  - **On-Demand Extraction Engine**: Scrape presets (`🔥 Tech & SaaS`, `🎮 India Gaming`, `💼 Finance`, `🎯 Sponsored Leads`), extraction methods, filter parameters, AI enrichment chip toggles, competitor benchmarking, and dark terminal log console.
  - **Background Autorunner Daemon**: Animated status pulse badge (`.pulse-dot`), threshold input (hours), daemon control toggle, live telemetry stat widgets (`Channels`, `Videos`, `Success Rate`, `API Quota`), and daemon telemetry log console.
- **Full-Screen Terminal Modal (`#terminalModal`)**:
  - Interactive terminal controls on both log consoles (`Clear`, `Copy`, `Expand ⤢`).
  - `Expand ⤢` pops open a 95% full-screen developer terminal console with syntax-colored output and keyboard <kbd>ESC</kbd> shortcut support.

---

## 5. Development Guidelines & Coding Rules

When modifying or expanding code in this project, adhere strictly to the following standards:

1. **Defensive Database Queries**:
   - Always verify table and column existence using `table_exists(conn, table_name)` and `get_table_columns(conn, table_name)` before executing SQL queries to ensure compatibility across workspace versions.
2. **Obey UI/Aesthetics Directives**:
   - Never use text emojis in HTML/JS components; use vector SVG icons.
   - Maintain the Office/Excel blue theme palette (`--excel-blue: #1056a0`, `--excel-light-blue: #f0f6fc`, `--excel-border: #d2d0ce`).
   - Use custom `showWinAlert` and `showWinPrompt` modals for user interactions.
3. **Workspace Isolation**:
   - Use `WorkspaceManager.get_db_path()` to obtain the active SQLite file path. Never hardcode single database file paths.
4. **Asynchronous Non-Blocking Workers**:
   - Long-running operations (channel extraction, AI pipeline analysis, autorunner loops) must run inside dedicated background threads (`threading.Thread`) and log output to thread-safe deque logs (`scrape_logs`, `autorunner_logs`).
5. **UI State Persistence**:
   - Maintain state across browser refreshes by synchronizing query parameters in URL history (`window.history.replaceState`) and `localStorage` (`yt_lead_generator_state`).

---

## 6. Common Operations & Commands

### Launching the Web Console
```bash
python web.py
```
*Access the interface at `http://localhost:5000`.*

### Running Standalone Scraper CLI
```bash
python main.py
```

### Running Background Autorunner Daemon CLI
```bash
python auto_run.py
```
