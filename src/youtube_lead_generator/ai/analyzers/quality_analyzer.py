import json

from youtube_lead_generator.ai.base_ai_service import BaseAIService
from youtube_lead_generator.ai.builders.creator_context_builder import CreatorContextBuilder
from youtube_lead_generator.ai.schemas.quality_schema import QualityProfile


class QualityAnalyzer(BaseAIService):

    def analyze(
        self,
        channel,
        videos,
        category,
        socials
    ):

        prompt = self.load_prompt(
            "quality.txt"
        )

        context = CreatorContextBuilder.build(
            channel,
            videos,
            category,
            socials
        )

        final_prompt = f"""
{prompt}

Creator Information

{json.dumps(context, indent=2)}
"""

        return self.ask(
            final_prompt,
            QualityProfile
        )
