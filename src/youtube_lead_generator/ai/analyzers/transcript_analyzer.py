from youtube_lead_generator.ai.base_ai_service import BaseAIService
from youtube_lead_generator.ai.schemas.transcript_schema import TranscriptProfile

class TranscriptAnalyzer(BaseAIService):
    def analyze(self, transcript_text: str):
        prompt = self.load_prompt("transcript.txt")
        final_prompt = f"{prompt}\n\nTranscript:\n{transcript_text}"
        return self.ask(final_prompt, TranscriptProfile)
