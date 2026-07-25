from pydantic import BaseModel, Field

class ThumbnailProfile(BaseModel):
    clickbait_score: int
    text_heavy: bool
    faces_present: bool
    vibe: str
    elements: list[str] = Field(default_factory=list)
