import json
from youtube_lead_generator.ai.base_ai_service import BaseAIService
from youtube_lead_generator.ai.schemas.benchmark_schema import BenchmarkProfile

class Benchmarker(BaseAIService):
    def analyze(self, creator_a_context: dict, creator_b_context: dict,
                activity_a: dict = None, activity_b: dict = None):
        prompt = self.load_prompt("benchmark.txt")

        context_a = creator_a_context.copy()
        context_b = creator_b_context.copy()

        if activity_a:
            context_a["activity"] = activity_a
        if activity_b:
            context_b["activity"] = activity_b

        final_prompt = f"""
{prompt}

Creator A:
{json.dumps(context_a, indent=2)}

Creator B:
{json.dumps(context_b, indent=2)}
"""
        return self.ask(final_prompt, BenchmarkProfile)
