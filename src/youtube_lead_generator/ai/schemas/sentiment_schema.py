from pydantic import BaseModel, Field

class SentimentProfile(BaseModel):
    overall_sentiment: str
    common_themes: list[str] = Field(default_factory=list)
    audience_questions: list[str] = Field(default_factory=list)
    negativity_score: int
