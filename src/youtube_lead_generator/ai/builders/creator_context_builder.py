from statistics import mean


class CreatorContextBuilder:

    @staticmethod
    def build(
        channel: dict,
        videos: list,
        category: dict,
        socials: dict
    ) -> dict:

        avg_views = (
            int(mean(v["views"] for v in videos))
            if videos else 0
        )

        avg_likes = (
            int(mean(v["likes"] for v in videos))
            if videos else 0
        )

        avg_comments = (
            int(mean(v["comments"] for v in videos))
            if videos else 0
        )

        tags = sorted({
            tag
            for video in videos
            for tag in video.get("tags", [])
        })

        return {

            "channel": {

                "name": channel["channel_name"],
                "description": channel["description"],
                "country": channel["country"],
                "joined_date": channel["joined_date"],
                "subscriber_count": channel["subscriber_count"],
                "total_views": channel["total_views"],
                "total_videos": channel["total_videos"]

            },

            "category": category,

            "socials": socials,

            "metrics": {

                "average_views": avg_views,
                "average_likes": avg_likes,
                "average_comments": avg_comments

            },

            "videos": [

                {
                    "title": video["title"],
                    "description": video["description"],
                    "tags": video["tags"],
                    "views": video["views"],
                    "likes": video["likes"],
                    "comments": video["comments"]
                }

                for video in videos

            ],

            "all_tags": tags

        }