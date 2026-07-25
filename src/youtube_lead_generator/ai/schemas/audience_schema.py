from pydantic import BaseModel, Field



class AudienceProfile(BaseModel):


    age_groups: list[str] = Field(
        default_factory=list
    )


    gender_split: str | None = None


    regions: list[str] = Field(
        default_factory=list
    )


    languages: list[str] = Field(
        default_factory=list
    )


    audience_personas: list[str] = Field(
        default_factory=list
    )


    interests: list[str] = Field(
        default_factory=list
    )


    motivations: list[str] = Field(
        default_factory=list
    )


    buying_intent: str | None = None


    purchase_categories: list[str] = Field(
        default_factory=list
    )


    audience_type: str | None = None


    skill_level: str | None = None


    spending_power: str | None = None


    community_strength: str | None = None


    confidence: int

    evidence:list[str]