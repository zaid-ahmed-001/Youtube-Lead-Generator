from youtube_transcript_api import YouTubeTranscriptApi

class TranscriptExtractor:

    @staticmethod
    def get_transcript(video_id):
        try:
            transcript_list = YouTubeTranscriptApi().fetch(video_id)
            text = " ".join([t.text for t in transcript_list])
            return text
        except Exception as e:
            print(f"Could not fetch transcript for {video_id}: {e}")
            return None
