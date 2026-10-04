"""
auto_run.py — Continuous keyword-based channel scraping

This script continuously searches for channels based on keywords
and scrapes them until stopped by the user (Ctrl+C).

Configuration is loaded from auto_config.py
"""

import os
import time
import sys

from youtube_lead_generator.core.database import (
    insert_scrape_run, insert_channel, insert_videos, 
    insert_video_deep_analysis, should_rescrape
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

# Initialize services
channel_service = ChannelService()
video_service = VideoService()
stats_service = VideoStatisticsService()


# ═════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def extract_channel_data(handle):
    """Fetch channel, videos, category, and social media data."""
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


def analyze_and_save_channel(handle, run_id, do_deep=False, deep_limit=0):
    """
    Analyze a single channel and save results to database.
    Returns the channel_row_id if successful, None otherwise.
    """
    print(f"\n{'='*80}")
    print(f"Processing channel: {handle}")
    print(f"{'='*80}")
    
    channel, videos, category, socials = extract_channel_data(handle)
    
    if not channel:
        print(f"[ERROR] Channel '{handle}' not found or unavailable.")
        return None
    
    channel_id = channel["channel_id"]
    
    print(f"[OK] Channel: {channel['channel_name']}")
    print(f"  Subscribers: {channel.get('subscriber_count', 0):,}")
    print(f"  Total Videos: {len(videos)}")
    
    # Run AI analyzers
    print("\n[1/6] Creator Profile...")
    profile = CreatorProfileAnalyzer().analyze(channel, videos, category, socials)
    
    print("[2/6] Audience Analysis...")
    audience_comments = []
    audience_transcripts = []
    top_audience_videos = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:5]
    for video in top_audience_videos:
        video_id = video["video_id"]
        comments = CommentService.get_top_comments(video_id, max_results=20)
        audience_comments.extend(comments)
        transcript = TranscriptExtractor.get_transcript(video_id)
        if transcript:
            audience_transcripts.append(transcript)
    audience = AudienceAnalyzer().analyze(channel, videos, audience_comments, audience_transcripts)
    
    print("[3/6] Brand Detection...")
    brands = BrandDetector().analyze(channel, videos, category, socials)
    
    print("[4/6] Quality Analysis...")
    quality = QualityAnalyzer().analyze(channel, videos, category, socials)
    
    print("[5/6] Sponsorship Analysis...")
    sponsorship = SponsorshipAnalyzer().analyze(channel, videos, category, socials)
    
    print("[6/6] Activity Analysis...")
    activity = ActivityStatus.analyze(videos)
    
    # Save to database
    print("\n[DB] Saving channel data...")
    channel_row_id = insert_channel(
        run_id=run_id,
        channel=channel,
        category=category,
        profile=profile,
        quality=quality,
        sponsorship=sponsorship,
        audience=audience,
        brands=brands,
        activity=activity,
    )
    video_id_map = insert_videos(channel_row_id, videos)
    print(f"[SAVED] Channel '{channel['channel_name']}' saved (row {channel_row_id}), {len(videos)} videos saved.")
    
    # Deep analysis if requested
    if do_deep and deep_limit > 0:
        print(f"\n--- Deep Content Analysis (Top {deep_limit} Videos) ---")
        top_videos = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:deep_limit]
        
        for idx, video in enumerate(top_videos):
            vid_id = video["video_id"]
            print(f"\nAnalyzing Video {idx+1}: {video['title'][:60]}...")
            
            t_profile = None
            s_profile = None
            thumb_profile = None
            
            # Transcript
            transcript = TranscriptExtractor.get_transcript(vid_id)
            if transcript:
                print("  [Transcript Analyzer]")
                t_profile = TranscriptAnalyzer().analyze(transcript)
            
            # Comments / Sentiment
            comments = CommentService.get_top_comments(vid_id, max_results=20)
            if comments:
                print("  [Comment Sentiment Analyzer]")
                s_profile = SentimentAnalyzer().analyze(comments)
            
            # Thumbnail
            thumb_path = ThumbnailExtractor.download_thumbnail(vid_id)
            if thumb_path:
                print("  [Thumbnail Analyzer]")
                try:
                    thumb_profile = ThumbnailAnalyzer().analyze(thumb_path)
                except Exception as e:
                    print(f"   Error analyzing thumbnail: {e}")
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
            
            # Save deep analysis
            if t_profile or s_profile or thumb_profile:
                video_row_id = video_id_map.get(vid_id)
                if video_row_id:
                    insert_video_deep_analysis(video_row_id, t_profile, s_profile, thumb_profile)
                    print(f"  [SAVED] Deep analysis saved for video {vid_id}.")
    
    return channel_row_id


# ═════════════════════════════════════════════════════════════════════════════
# MAIN AUTO-RUN LOOP
# ═════════════════════════════════════════════════════════════════════════════

def run_auto_mode():
    """
    Continuously search for channels based on keywords in auto_config.py
    and scrape them until user stops (Ctrl+C).
    """
    try:
        import youtube_lead_generator.core.auto_config as cfg
    except ImportError:
        print("[ERROR] auto_config.py not found. Please create it first.")
        return
    
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║            AUTO-RUN MODE - CONTINUOUS SCRAPING                    ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print(f"\nConfiguration:")
    print(f"   Keywords: {cfg.KEYWORDS}")
    print(f"   Region: {cfg.REGION_CODE or 'Global'}")
    print(f"   Sort: {cfg.SORT_ORDER}")
    print(f"   Max channels per search: {cfg.MAX_CHANNELS_PER_SEARCH}")
    print(f"   Re-scrape threshold: {cfg.RESCRAPE_THRESHOLD_HOURS} hours")
    print(f"   Delay between channels: {cfg.DELAY_BETWEEN_CHANNELS}s")
    print(f"   Deep analysis: {cfg.DO_DEEP_ANALYSIS}")
    if cfg.DO_DEEP_ANALYSIS:
        print(f"   Deep analysis limit: {cfg.DEEP_ANALYSIS_LIMIT} videos")
    print(f"\n[NOTICE] Press Ctrl+C at any time to stop.\n")
    
    time.sleep(2)  # Give user time to read
    
    processed_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        while True:
            # Create a new run for this cycle
            combined_query = " ".join(cfg.KEYWORDS)
            run_id = insert_scrape_run(
                search_query=combined_query,
                region_code=cfg.REGION_CODE,
                sort_order=cfg.SORT_ORDER,
            )
            
            search_target = getattr(cfg, 'SEARCH_TARGET', 'video')
            print(f"\n[SEARCH] Searching for channels matching: '{combined_query}' (Target: {search_target})...")
            
            # Search for channels
            channels = channel_service.search_channels(
                combined_query,
                cfg.SORT_ORDER,
                cfg.MAX_CHANNELS_PER_SEARCH,
                cfg.REGION_CODE,
                search_target=search_target
            )
            
            if not channels:
                print("[NOTICE] No channels found. Waiting 30 seconds before next search...")
                time.sleep(30)
                continue
            
            print(f"[OK] Found {len(channels)} channels")
            
            # Process each channel
            for idx, ch_info in enumerate(channels):
                handle = ch_info.get("handle")
                channel_id = ch_info.get("channel_id")
                channel_name = ch_info.get("channel_name", "Unknown")
                
                if not handle or not channel_id:
                    print(f"\n[{idx+1}/{len(channels)}] [SKIP] Skipping channel (missing handle/ID)")
                    error_count += 1
                    continue
                
                print(f"\n[{idx+1}/{len(channels)}] Checking: {channel_name} (@{handle})")
                
                # Check if we should rescrape
                if not should_rescrape(channel_id, cfg.RESCRAPE_THRESHOLD_HOURS):
                    print(f"  [SKIP] Skipped (scraped recently)")
                    skipped_count += 1
                    time.sleep(1)  # Small delay even for skipped
                    continue
                
                # Analyze and save
                try:
                    channel_row_id = analyze_and_save_channel(
                        handle,
                        run_id,
                        do_deep=cfg.DO_DEEP_ANALYSIS,
                        deep_limit=cfg.DEEP_ANALYSIS_LIMIT
                    )
                    
                    if channel_row_id:
                        processed_count += 1
                        print(f"\n[SUCCESS] Successfully processed! (Total: {processed_count})")
                    else:
                        error_count += 1
                        print(f"\n[ERROR] Failed to process channel")
                    
                except Exception as e:
                    error_count += 1
                    print(f"\n[ERROR] Error processing channel: {e}")
                
                # Delay between channels to avoid rate limits
                if idx < len(channels) - 1:  # Don't delay after last channel
                    print(f"\n[WAIT] Waiting {cfg.DELAY_BETWEEN_CHANNELS}s before next channel...")
                    time.sleep(cfg.DELAY_BETWEEN_CHANNELS)
            
            # Summary after each batch
            print(f"\n{'─'*80}")
            print(f"Batch Summary:")
            print(f"   Processed: {processed_count} | Skipped: {skipped_count} | Errors: {error_count}")
            print(f"{'─'*80}")
            
            # Small delay before next search cycle
            print(f"\n[WAIT] Waiting 10s before next search cycle...")
            time.sleep(10)
    
    except KeyboardInterrupt:
        print(f"\n\n[STOP] Auto-run stopped by user.")
        print(f"\nFinal Statistics:")
        print(f"   Total Processed: {processed_count}")
        print(f"   Total Skipped: {skipped_count}")
        print(f"   Total Errors: {error_count}")
        print(f"\nGoodbye!\n")


# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

run_autorunner = run_auto_mode

if __name__ == "__main__":
    run_autorunner()
