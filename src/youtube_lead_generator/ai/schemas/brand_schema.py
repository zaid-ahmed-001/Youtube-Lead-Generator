from pydantic import BaseModel, Field


class BrandProfile(BaseModel):

    brands: list[str] = Field(default_factory=list)

    games: list[str] = Field(default_factory=list)

    software: list[str] = Field(default_factory=list)

    hardware: list[str] = Field(default_factory=list)

    technologies: list[str] = Field(default_factory=list)

    creators: list[str] = Field(default_factory=list)

    confidence: int