import json
from youtube_lead_generator.ai.base_ai_service import BaseAIService
from youtube_lead_generator.ai.schemas.sentiment_schema import SentimentProfile

class SentimentAnalyzer(BaseAIService):
    def analyze(self, comments: list):
        prompt = self.load_prompt("sentiment.txt")
        final_prompt = f"{prompt}\n\nComments:\n{json.dumps(comments, indent=2)}"
        return self.ask(final_prompt, SentimentProfile)
