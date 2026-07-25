from statistics import mean


class AudienceContextBuilder:

    @staticmethod
    def build(
        channel,
        videos,
        comments,
        transcripts
    ):

        avg_views = (
            int(mean(v["views"] for v in videos))
            if videos else 0
        )

        avg_comments = (
            int(mean(v["comments"] for v in videos))
            if videos else 0
        )


        engagement_rate = (
            (avg_comments / avg_views) * 100
            if avg_views > 0
            else 0.0
        )

        return {

            "creator": {

                "name": channel["channel_name"],
                "description": channel["description"],
                "country": channel["country"],
                "subscriber_count": channel["subscriber_count"]

            },


            "engagement": {
                "comment_rate": round(engagement_rate,2)    
            },
            
            "content": {

                "topics": [
                    v["title"]
                    for v in videos
                ],

                "tags": list({
                    tag
                    for v in videos
                    for tag in v.get("tags", [])
                })

            },


            "performance": {

                "average_views": avg_views,
                "average_comments": avg_comments,
                "subscriber_count":
                    channel["subscriber_count"]

            },


            "viewer_comments": comments,


            "transcripts": transcripts

        }