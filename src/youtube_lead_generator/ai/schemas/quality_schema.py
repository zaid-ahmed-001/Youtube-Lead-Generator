from pydantic import BaseModel


class QualityProfile(BaseModel):

    professionalism: int

    production_quality: int

    branding: int

    consistency: int

    originality: int

    family_friendly: bool

    advertiser_friendly: bool

    confidence: int