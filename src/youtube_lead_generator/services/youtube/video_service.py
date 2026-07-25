from youtube_lead_generator.core.youtube_client import youtube


class VideoService:

    def get_uploads(self, uploads_playlist_id, max_results=50):

        videos = []
        next_page_token = None

        while True:

            request = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=min(max_results, 50),
                pageToken=next_page_token
            )

            response = request.execute()

            for item in response["items"]:

                videos.append({
                    "video_id": item["contentDetails"]["videoId"],
                    "title": item["snippet"]["title"],
                    "published_at": item["contentDetails"]["videoPublishedAt"]
                })

            next_page_token = response.get("nextPageToken")

            if not next_page_token or len(videos) >= max_results:
                break

        return videos[:max_results]