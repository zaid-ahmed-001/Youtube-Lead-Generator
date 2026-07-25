from pathlib import Path

from youtube_lead_generator.ai.clients.gemini_client import GeminiClient


class BaseAIService:

    def __init__(self):

        self.client = GeminiClient()

    def load_prompt(self, filename):

        path = (
            Path(__file__).parent
            / "prompts"
            / filename
        )

        return path.read_text(
            encoding="utf-8"
        )

    def ask(
        self,
        prompt,
        schema,
        image_path=None
    ):

        return self.client.generate(
            prompt,
            schema,
            image_path=image_path
        )