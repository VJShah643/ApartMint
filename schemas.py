from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Canonical search preferences extracted from a user utterance."""

    city: Optional[str] = Field(default=None, description="Primary city name, e.g., Uppsala")
    areas: List[str] = Field(default_factory=list, description="Neighborhoods/areas within the city")
    minRooms: Optional[int] = Field(default=None, description="Minimum number of rooms")
    maxRooms: Optional[int] = Field(default=None, description="Maximum number of rooms")
    maxRent: Optional[int] = Field(default=None, description="Maximum monthly rent in SEK")
    keywords: List[str] = Field(default_factory=list, description="Free-form keywords like 'balcony', 'elevator'")
    sources: List[str] = Field(
        default_factory=list,
        description="Listing sources to query, e.g., ['heimstaden','bostad']",
    )
    summary: Optional[str] = Field(
        default=None, description="Short NL summary of the interpreted search"
    )


SUPPORTED_SOURCES = ["heimstaden", "bostad"]
