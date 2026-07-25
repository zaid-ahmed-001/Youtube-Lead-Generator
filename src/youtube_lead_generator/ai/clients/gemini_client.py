from google import genai
from google.genai import types

from youtube_lead_generator.core.config import GEMINI_API_KEY, MODEL


class GeminiClient:

    def __init__(self):

        self.client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        self.model = MODEL

    def generate(
        self,
        prompt: str,
        schema,
        image_path: str = None
    ):

        contents = [prompt]
        if image_path:
            with open(image_path, 'rb') as f:
                contents.append(
                    types.Part.from_bytes(
                        data=f.read(),
                        mime_type='image/jpeg',
                    )
                )

        response = self.client.models.generate_content(

            model=self.model,

            contents=contents,

            config=types.GenerateContentConfig(

                temperature=0.2,

                response_mime_type="application/json",

                response_schema=schema

            )

        )

        return response.parsed