import isodate

from youtube_lead_generator.core.youtube_client import youtube


class VideoStatisticsService:

    def get_video_statistics(self, video_ids):

        request = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids)
        )

        response = request.execute()

        videos = []

        for item in response["items"]:

            snippet = item["snippet"]
            stats = item.get("statistics", {})
            details = item["contentDetails"]

            duration = isodate.parse_duration(
                details["duration"]
            )

            duration_seconds = int(duration.total_seconds())

            duration_minutes = round(
                duration_seconds / 60,
                2
            )

            videos.append({
                "video_id": item["id"],
                "title": snippet["title"],
                "published_at": snippet["publishedAt"],
                "description": snippet["description"],
                "category_id": snippet["categoryId"],
                "tags": snippet.get("tags", []),

                "duration": details["duration"],
                "duration_seconds": duration_seconds,
                "duration_minutes": duration_minutes,
                "is_short": duration_seconds <= 60,

                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0))
            })

        return videos