from datetime import datetime, timezone
from statistics import mean


class ActivityStatus:

    @staticmethod
    def _expected_gap(avg_duration_minutes: float) -> int:
        """
        Expected upload frequency based on average video length.
        """

        if avg_duration_minutes <= 3:
            return 3          # Shorts

        elif avg_duration_minutes <= 8:
            return 7          # Short videos

        elif avg_duration_minutes <= 15:
            return 14         # Medium videos

        elif avg_duration_minutes <= 30:
            return 21         # Long videos

        elif avg_duration_minutes <= 60:
            return 30         # Very long videos

        else:
            return 45         # Podcasts / Documentaries

    @staticmethod
    def analyze(videos):

        today = datetime.now(timezone.utc)

        if not videos:
            return {
                "status": "Unknown"
            }

        # ---------------------------------------------------
        # Sort upload dates
        # ---------------------------------------------------

        dates = sorted(
            [
                datetime.fromisoformat(
                    video["published_at"].replace("Z", "+00:00")
                )
                for video in videos
            ],
            reverse=True
        )

        # ---------------------------------------------------
        # Last upload
        # ---------------------------------------------------

        last_upload_days = (today - dates[0]).days

        # ---------------------------------------------------
        # Upload counts
        # ---------------------------------------------------

        uploads_last_30 = sum(
            1
            for d in dates
            if (today - d).days <= 30
        )

        uploads_last_90 = sum(
            1
            for d in dates
            if (today - d).days <= 90
        )

        uploads_last_year = sum(
            1
            for d in dates
            if (today - d).days <= 365
        )

        # ---------------------------------------------------
        # Upload gaps
        # ---------------------------------------------------

        gaps = [
            (dates[i] - dates[i + 1]).days
            for i in range(len(dates) - 1)
        ]

        average_gap = (
            mean(gaps)
            if gaps
            else 0
        )

        # ---------------------------------------------------
        # Average duration
        # ---------------------------------------------------

        durations = [
            video.get("duration_minutes", 0)
            for video in videos
        ]

        average_duration = (
            mean(durations)
            if durations
            else 0
        )

        expected_gap = ActivityStatus._expected_gap(
            average_duration
        )

        frequency_ratio = (
            average_gap / expected_gap
            if expected_gap
            else 0
        )

        # ---------------------------------------------------
        # Revived detection
        # ---------------------------------------------------

        revived = (
            len(gaps) > 0
            and max(gaps) > 365
            and last_upload_days <= expected_gap
        )

        # ---------------------------------------------------
        # Consistency Score
        # ---------------------------------------------------

        if gaps:

            variance = mean(
                abs(g - average_gap)
                for g in gaps
            )

            consistency_score = max(
                0,
                min(
                    100,
                    round(
                        100 - variance
                    )
                )
            )

        else:

            consistency_score = 100

        # ---------------------------------------------------
        # Activity Score
        # ---------------------------------------------------

        activity_score = 100

        # Penalize inactivity

        activity_score -= min(
            last_upload_days * 0.35,
            40
        )

        # Penalize upload frequency

        if frequency_ratio > 1:

            activity_score -= min(
                (frequency_ratio - 1) * 20,
                40
            )

        # Reward recent uploads

        if uploads_last_30 >= 4:
            activity_score += 8

        elif uploads_last_30 >= 2:
            activity_score += 5

        # Slight reward for consistency

        activity_score += consistency_score * 0.15

        activity_score = round(
            max(
                0,
                min(100, activity_score)
            )
        )

        # ---------------------------------------------------
        # Status
        # ---------------------------------------------------

        if revived:

            status = "Revived"

        elif activity_score >= 90:

            status = "Excellent"

        elif activity_score >= 75:

            status = "Healthy"

        elif activity_score >= 55:

            status = "Active"

        elif activity_score >= 35:

            status = "Dormant"

        else:

            status = "Dead"

        # ---------------------------------------------------
        # Upload Frequency Label
        # ---------------------------------------------------

        if average_gap <= expected_gap:

            upload_frequency = "Consistent"

        elif average_gap <= expected_gap * 1.5:

            upload_frequency = "Slightly Irregular"

        else:

            upload_frequency = "Irregular"

        return {

            "status": status,

            "activity_score": activity_score,

            "consistency_score": consistency_score,

            "revived": revived,

            "last_upload_days": last_upload_days,

            "uploads_last_30_days": uploads_last_30,

            "uploads_last_90_days": uploads_last_90,

            "uploads_last_year": uploads_last_year,

            "average_video_duration_minutes": round(
                average_duration,
                2
            ),

            "expected_upload_gap_days": expected_gap,

            "actual_upload_gap_days": round(
                average_gap,
                1
            ),

            "upload_frequency": upload_frequency,

            "frequency_ratio": round(
                frequency_ratio,
                2
            )
        }