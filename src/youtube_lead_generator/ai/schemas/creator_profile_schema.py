from pydantic import BaseModel, Field


class CreatorProfile(BaseModel):

    primary_niche: str | None = None

    secondary_niche: str | None = None

    industry: str | None = None

    content_styles: list[str] = Field(default_factory=list)

    target_audience: str | None = None

    experience_level: str | None = None

    primary_language: str | None = None

    family_friendly: bool

    brand_friendly: bool

    confidence: int