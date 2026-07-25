import json

from youtube_lead_generator.ai.base_ai_service import BaseAIService
from youtube_lead_generator.ai.builders.audience_context_builder import AudienceContextBuilder
from youtube_lead_generator.ai.schemas.audience_schema import AudienceProfile



class AudienceAnalyzer(BaseAIService):


    def analyze(
        self,
        channel,
        videos,
        comments,
        transcripts
    ):


        prompt = self.load_prompt(
            "audience.txt"
        )


        context = AudienceContextBuilder.build(
            channel,
            videos,
            comments,
            transcripts
        )


        final_prompt = f"""

{prompt}


Audience Data:

{json.dumps(context, indent=2)}

"""


        return self.ask(
            final_prompt,
            AudienceProfile
        )