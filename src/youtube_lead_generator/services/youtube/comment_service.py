from youtube_lead_generator.core.youtube_client import youtube

class CommentService:

    @staticmethod
    def get_top_comments(video_id, max_results=20):
        try:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=max_results,
                order="relevance"
            )
            response = request.execute()
            
            comments = []
            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append(snippet["textOriginal"])
                
            return comments
        except Exception as e:
            print(f"Could not fetch comments for {video_id}: {e}")
            return []
