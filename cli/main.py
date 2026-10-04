import os
import json
import time
import sys

from youtube_lead_generator.core.database import (
    insert_scrape_run, insert_channel, insert_videos, 
    insert_video_deep_analysis, insert_benchmark,
    should_rescrape
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

def run_cli():
    channel_service = ChannelService()
    video_service = VideoService()
    stats_service = VideoStatisticsService()

    # --- Configuration ---
    COUNTRY_CODES = {
        "india": "IN", "usa": "US", "us": "US", "uk": "GB", "united kingdom": "GB",
        "canada": "CA", "australia": "AU", "germany": "DE", "france": "FR",
        "japan": "JP", "brazil": "BR", "mexico": "MX"
    }

    method = input("Search by keyword or enter direct handle? (search/handle): ").strip().lower()

    if method == "search":
        keyword_input = input("Enter keyword(s) separated by commas: ").strip()
        keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]
        
        order_input = input("Sort by (popular/new/featured): ").strip().lower()
        
        order_map = {
            "popular": "viewCount",
            "new": "date",
            "featured": "relevance"
        }
        order = order_map.get(order_input, "relevance")
        
        region_input = input("Enter region (e.g., usa, india) or leave blank for global: ").strip().lower()
        region_code = None
        if region_input:
            region_code = COUNTRY_CODES.get(region_input, region_input.upper())
            if len(region_code) != 2:
                print(f"Warning: Invalid region '{region_input}'. Ignoring region filter.")
                region_code = None
                
        max_results_str = input("Enter top N channels to fetch (default 5): ").strip()
        try:
            max_results = int(max_results_str) if max_results_str else 5
        except ValueError:
            print(f"Invalid number '{max_results_str}'. Using default of 5.")
            max_results = 5
        
        combined_query = " ".join(keywords)

        print(f"\nSearching for '{combined_query}'...")
        final_channels = channel_service.search_channels(combined_query, order, max_results, region_code)

        if not final_channels:
            print("No channels found.")
            sys.exit(1)
            
        print("\nChannels found:")
        for i, c in enumerate(final_channels):
            print(f"[{i+1}] {c['channel_name']} (@{c['handle']}) - {c['subscriber_count']:,} subs | {c['total_views']:,} views")
            
        choice = input("\nEnter the number of the channel to analyze: ").strip()
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(final_channels):
                CHANNEL_HANDLE = final_channels[choice_idx]['handle']
            else:
                print("Invalid choice.")
                sys.exit(1)
        except ValueError:
            print("Invalid input.")
            sys.exit(1)
    else:
        CHANNEL_HANDLE = input("Enter channel handle: ").strip()
        combined_query = None
        region_code = None
        order = None

    # Create a scrape_run record for this session
    RUN_ID = insert_scrape_run(
        search_query=combined_query if method == "search" else None,
        region_code=region_code    if method == "search" else None,
        sort_order=order           if method == "search" else None,
    )
    print(f"\n[DB] Scrape run #{RUN_ID} started.")

    # AI Enrichment Toggle
    ENABLE_AI = input("Enable Gemini AI enrichment? (y/n, default y): ").strip().lower() != "n"

    # Deep Analysis Settings
    DO_DEEP_ANALYSIS = (input("Run deep content analysis? (y/n): ").strip().lower() == "y") if ENABLE_AI else False
    DEEP_ANALYSIS_LIMIT = int(input("How many top videos to analyze? ").strip()) if DO_DEEP_ANALYSIS else 0

    # Benchmarking Settings
    DO_BENCHMARKING = (input("Run competitor benchmarking? (y/n): ").strip().lower() == "y") if ENABLE_AI else False
    COMPETITOR_HANDLE = input("Enter competitor handle: ").strip() if DO_BENCHMARKING else None

    def extract_channel_data(handle):
        channel = channel_service.get_channel(handle)
        if not channel:
            return None, None, None, None
        uploads = video_service.get_uploads(channel["uploads_playlist"], max_results=20)
        video_ids = [video["video_id"] for video in uploads]
        videos = stats_service.get_video_statistics(video_ids)
        category = CategoryExtractor.extract(videos)
        texts = [channel["description"]]
        texts.extend(video["description"] for video in videos)
        socials = SocialExtractor.extract(texts)
        return channel, videos, category, socials

    print(f"Fetching data for main channel: {CHANNEL_HANDLE}...")
    channel, videos, category, socials = extract_channel_data(CHANNEL_HANDLE)

    if not channel:
        print("Channel not found.")
        sys.exit(1)

    profile, audience, brands, quality, sponsorship = None, None, None, None, None

    if ENABLE_AI:
        try:
            print("\n--- Creator Profile ---")
            profile = CreatorProfileAnalyzer().analyze(channel, videos, category, socials)
            print(profile)

            print("\n--- Audience ---")
            audience_comments = []
            audience_transcripts = []
            top_audience_videos = sorted(
                videos,
                key=lambda v: v.get("views", 0),
                reverse=True
            )[:5]

            for video in top_audience_videos:
                video_id = video["video_id"]
                comments = CommentService.get_top_comments(video_id, max_results=20)
                audience_comments.extend(comments)
                transcript = TranscriptExtractor.get_transcript(video_id)
                if transcript:
                    audience_transcripts.append(transcript)

            audience = AudienceAnalyzer().analyze(
                channel,
                videos,
                audience_comments,
                audience_transcripts
            )
            print(audience)

            print("\n--- Brands ---")
            brands = BrandDetector().analyze(channel, videos, category, socials)
            print(brands)

            print("\n--- Quality ---")
            quality = QualityAnalyzer().analyze(channel, videos, category, socials)
            print(quality)

            print("\n--- Sponsorship ---")
            sponsorship = SponsorshipAnalyzer().analyze(channel, videos, category, socials)
            print(sponsorship)
        except Exception as e:
            print(f"\n[AI Warning] Gemini AI enrichment failed/skipped: {e}")
            print("Proceeding with pure YouTube channel data extraction.")
    else:
        print("\n[AI Bypass] Skipping Gemini AI analyzers. Extracting pure YouTube Data.")

    print("\n--- Activity ---")
    activity = ActivityStatus.analyze(videos)
    print(activity)

    print("\n[DB] Saving channel data...")
    CHANNEL_ROW_ID = insert_channel(
        run_id=RUN_ID,
        channel=channel,
        category=category,
        profile=profile,
        quality=quality,
        sponsorship=sponsorship,
        audience=audience,
        brands=brands,
        activity=activity,
    )
    VIDEO_ID_MAP = insert_videos(CHANNEL_ROW_ID, videos)
    print(f"[DB] Channel '{channel['channel_name']}' saved (row {CHANNEL_ROW_ID}), {len(videos)} videos saved.")

    if DO_DEEP_ANALYSIS:
        print(f"\n--- Deep Content Analysis (Top {DEEP_ANALYSIS_LIMIT} Videos) ---")
        top_videos = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:DEEP_ANALYSIS_LIMIT]
        
        for idx, video in enumerate(top_videos):
            vid_id = video["video_id"]
            print(f"\nAnalyzing Video {idx+1}: {video['title']}")
            
            t_profile = None
            s_profile = None
            thumb_profile = None
            
            transcript = TranscriptExtractor.get_transcript(vid_id)
            if transcript:
                print("  [Transcript Analyzer]")
                t_profile = TranscriptAnalyzer().analyze(transcript)
                print("  ", t_profile)
                
            comments = CommentService.get_top_comments(vid_id, max_results=20)
            if comments:
                print("  [Comment Sentiment Analyzer]")
                s_profile = SentimentAnalyzer().analyze(comments)
                print("  ", s_profile)
                
            thumb_path = ThumbnailExtractor.download_thumbnail(vid_id)
            if thumb_path:
                print("  [Thumbnail Analyzer]")
                try:
                    thumb_profile = ThumbnailAnalyzer().analyze(thumb_path)
                    print("  ", thumb_profile)
                except Exception as e:
                    print("   Error analyzing thumbnail:", e)
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)

            if t_profile or s_profile or thumb_profile:
                video_row_id = VIDEO_ID_MAP.get(vid_id)
                if video_row_id:
                    insert_video_deep_analysis(video_row_id, t_profile, s_profile, thumb_profile)
                    print(f"  [DB] Deep analysis saved for video {vid_id}.")

    if DO_BENCHMARKING and COMPETITOR_HANDLE:
        print(f"\n--- Benchmarking vs {COMPETITOR_HANDLE} ---")
        c_channel, c_videos, c_category, c_socials = extract_channel_data(COMPETITOR_HANDLE)
        if not c_channel:
            print(f"Could not fetch competitor {COMPETITOR_HANDLE}")
        else:
            ctx_a = CreatorContextBuilder.build(channel, videos, category, socials)
            ctx_b = CreatorContextBuilder.build(c_channel, c_videos, c_category, c_socials)

            activity_a = ActivityStatus.analyze(videos)
            activity_b = ActivityStatus.analyze(c_videos)

            benchmark_report = Benchmarker().analyze(ctx_a, ctx_b, activity_a, activity_b)
            print("\n--- Benchmark Report ---")
            print(benchmark_report)

            insert_benchmark(RUN_ID, CHANNEL_ROW_ID, COMPETITOR_HANDLE, benchmark_report)
            print(f"[DB] Benchmark vs '{COMPETITOR_HANDLE}' saved.")

if __name__ == "__main__":
    run_cli()