from pydantic import BaseModel, Field


class SponsorshipProfile(BaseModel):

    has_sponsorships: bool

    brands: list[str] = Field(default_factory=list)

    sponsorship_types: list[str] = Field(default_factory=list)

    affiliate_links: bool

    business_email_present: bool

    sponsorship_readiness: int

    confidence: int