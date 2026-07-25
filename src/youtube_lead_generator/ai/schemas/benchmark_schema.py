from pydantic import BaseModel, Field

class BenchmarkProfile(BaseModel):
    winner: str
    engagement_comparison: str
    audience_differences: str
    quality_differences: str
    activity_comparison: str
    growth_prediction: str
    content_gaps: list[str] = Field(default_factory=list)
