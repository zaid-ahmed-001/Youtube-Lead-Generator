from youtube_lead_generator.ai.base_ai_service import BaseAIService
from youtube_lead_generator.ai.schemas.thumbnail_schema import ThumbnailProfile

class ThumbnailAnalyzer(BaseAIService):
    def analyze(self, image_path: str):
        prompt = self.load_prompt("thumbnail.txt")
        return self.ask(prompt, ThumbnailProfile, image_path=image_path)
