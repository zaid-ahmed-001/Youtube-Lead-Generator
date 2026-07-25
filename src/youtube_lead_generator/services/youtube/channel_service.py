from youtube_lead_generator.core.youtube_client import youtube
import re


class ChannelService:

    def get_channel(self, handle: str):

        request = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            forHandle=handle
        )

        response = request.execute()

        if not response.get("items"):
            return None

        item = response["items"][0]

        snippet = item["snippet"]
        stats = item["statistics"]

        description = snippet.get("description", "")

        email = self.extract_email(description)

        return {

            "channel_id": item["id"],

            "channel_name": snippet["title"],

            "description": description,

            "joined_date": snippet["publishedAt"],

            "country": snippet.get("country"),

            "subscriber_count": int(stats.get("subscriberCount", 0)),

            "total_views": int(stats.get("viewCount", 0)),

            "total_videos": int(stats.get("videoCount", 0)),

            "email": email,

            "uploads_playlist": item["contentDetails"]["relatedPlaylists"]["uploads"]
        }

    def get_channel_by_id(self, channel_id: str):
        request = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=channel_id
        )
        response = request.execute()

        if not response.get("items"):
            return None

        item = response["items"][0]
        snippet = item["snippet"]
        stats = item["statistics"]
        description = snippet.get("description", "")
        email = self.extract_email(description)

        return {
            "channel_id": item["id"],
            "channel_name": snippet["title"],
            "description": description,
            "joined_date": snippet.get("publishedAt"),
            "country": snippet.get("country"),
            "subscriber_count": int(stats.get("subscriberCount", 0)),
            "total_views": int(stats.get("viewCount", 0)),
            "total_videos": int(stats.get("videoCount", 0)),
            "email": email,
            "uploads_playlist": item["contentDetails"]["relatedPlaylists"]["uploads"]
        }

    def search_channels(self, keyword: str, order: str = 'relevance', max_results: int = 5, region_code: str = None,
                        relevance_language: str = None, safe_search: str = None, published_after: str = None, published_before: str = None, topic_id: str = None):
        # The YouTube API is notoriously broken for sorting channels by viewCount.
        # To fix this, we fetch the top 50 relevant channels and sort them locally.
        fetch_limit = 50 if order in ['viewCount', 'date'] else max_results
        
        search_kwargs = {
            "part": "snippet",
            "type": "channel",
            "q": keyword,
            "order": "relevance",
            "maxResults": fetch_limit
        }
        
        if region_code:
            search_kwargs["regionCode"] = region_code
        if relevance_language:
            search_kwargs["relevanceLanguage"] = relevance_language
        if safe_search and safe_search != 'none':
            search_kwargs["safeSearch"] = safe_search
        if published_after:
            search_kwargs["publishedAfter"] = published_after
        if published_before:
            search_kwargs["publishedBefore"] = published_before
        if topic_id:
            search_kwargs["topicId"] = topic_id
            
        request = youtube.search().list(**search_kwargs)
        response = request.execute()
        
        if not response.get("items"):
            return []
            
        channel_ids = [item["snippet"]["channelId"] for item in response["items"]]
        
        channels_request = youtube.channels().list(
            part="snippet,statistics,brandingSettings",
            id=",".join(channel_ids)
        )

        channels_response = channels_request.execute()

        results = []

        for item in channels_response.get("items", []):

            snippet = item["snippet"]
            stats = item["statistics"]

            creator_country = (
                item.get("brandingSettings", {})
                .get("channel", {})
                .get("country")
            )

            if region_code:
                if not creator_country or creator_country.upper() != region_code.upper():
                    continue

            handle = snippet.get("customUrl", snippet["title"])

            if handle.startswith("@"):
                handle = handle[1:]

            results.append({
                "channel_id": item["id"],
                "channel_name": snippet["title"],
                "handle": handle,
                "country": creator_country,
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "total_views": int(stats.get("viewCount", 0)),
                "total_videos": int(stats.get("videoCount", 0)),
                "joined_date": snippet.get("publishedAt", "")
            })
            
        # Apply local sorting
        if order == 'viewCount':
            results.sort(key=lambda x: x["total_views"], reverse=True)
        elif order == 'date':
            results.sort(key=lambda x: x["joined_date"], reverse=True)
        else:
            # Maintain API's relevance order
            ordered_results = []
            for cid in channel_ids:
                for r in results:
                    if r["channel_id"] == cid:
                        ordered_results.append(r)
                        break
            results = ordered_results
                    
        return results[:max_results]

    @staticmethod
    def extract_email(text):

        emails = re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            text
        )

        return emails[0] if emails else None