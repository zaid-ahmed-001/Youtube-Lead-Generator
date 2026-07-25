from pydantic import BaseModel, Field

class TranscriptProfile(BaseModel):
    core_topics: list[str] = Field(default_factory=list)
    has_sponsor_pitch: bool
    sponsor_pitch_style: str | None = None
    call_to_actions: list[str] = Field(default_factory=list)
