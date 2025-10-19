from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from pydantic import ValidationError

from schemas import SearchQuery, SUPPORTED_SOURCES


load_dotenv()


class LLMUnavailable(Exception):
    pass


def _get_gemini_client():
    """Return a Gemini client instance if available, else raise LLMUnavailable."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    if not api_key:
        raise LLMUnavailable("Missing GEMINI_API_KEY in environment")
    try:
        import google.generativeai as genai  # type: ignore
    except Exception as e:
        raise LLMUnavailable(f"Gemini SDK not installed: {e}")
    genai.configure(api_key=api_key)
    return genai


SYS_PROMPT = (
    "You are a strict JSON API. Extract structured apartment search preferences from the user message. "
    "Return ONLY a JSON object with fields: city (string|null), areas (string[]), minRooms (int|null), maxRooms (int|null), "
    "maxRent (int|null), keywords (string[]), sources (string[] from ['heimstaden','bostad']), summary (string). "
    "Cities and areas should be capitalized as proper nouns. Prices are monthly SEK if unspecified. Rooms are integer count. "
    "Interpret phrases like 'at least 2 rooms' -> minRooms=2; 'at most 2 rooms' or '<=2 rooms' -> maxRooms=2. "
    "Use conservative inference; if unsure, leave fields null or empty."
)


def parse_search_query(message: str, supported_cities: List[str]) -> SearchQuery:
    """Use Gemini to parse a user message into a SearchQuery. Falls back to heuristics if LLM unavailable."""
    try:
        genai = _get_gemini_client()
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        # Provide a lightweight schema hint in the prompt; in production, consider JSON schema tools/function calling.
        prompt = (
            f"System: {SYS_PROMPT}\n\n"
            f"Supported cities: {supported_cities}. Supported sources: {SUPPORTED_SOURCES}.\n"
            f"User: {message}\n"
            f"Return JSON only."
        )
        resp = model.generate_content(prompt)
        text = resp.text if hasattr(resp, "text") else (resp.candidates[0].content.parts[0].text if resp.candidates else "{}")
        data = json.loads(text)
        # Validate and coerce with Pydantic
        sq = SearchQuery(**data)
        # Default sources if omitted
        if not sq.sources:
            sq.sources = SUPPORTED_SOURCES.copy()
        return sq
    except (LLMUnavailable, Exception):
        # Fallback: minimal heuristic extraction mirroring current backend behavior
        import re

        budget = None
        min_rooms = None
        max_rooms = None
        city = None
        # budget
        m = re.search(r"(\d{4,6})\s*(?:kr|sek|:-|/mo|per\s*month)?", message, flags=re.I)
        if m:
            budget = int(m.group(1))
        # rooms (min/max)
        # at most / <= / max 2 rooms
        m = re.search(r"(?:at\s*most|<=|max)\s*(\d)\s*(?:rum|rooms?|br|r|bed)\b", message, flags=re.I)
        if m:
            max_rooms = int(m.group(1))
        # at least / >= / min 2 rooms
        m = re.search(r"(?:at\s*least|>=|min)\s*(\d)\s*(?:rum|rooms?|br|r|bed)\b", message, flags=re.I)
        if m:
            min_rooms = int(m.group(1))
        # plain 'N rooms' without qualifier → treat as exactly N (both min and max)
        if min_rooms is None and max_rooms is None:
            m = re.search(r"(\d)\s*(?:rum|rooms?|br|r|bed)\b", message, flags=re.I)
            if m:
                num = int(m.group(1))
                min_rooms = num
                max_rooms = num
        # city from provided list
        for c in supported_cities:
            if re.search(rf"\b{re.escape(c)}\b", message, flags=re.I):
                city = c
                break
        # keywords simple pass-through tokens
        keywords: List[str] = []
        for token in ["balcony", "elevator", "student", "central", "pets", "furnished"]:
            if re.search(token, message, flags=re.I):
                keywords.append(token)

        return SearchQuery(
            city=city,
            areas=[],
            minRooms=min_rooms,
            maxRooms=max_rooms,
            maxRent=budget,
            keywords=keywords,
            sources=SUPPORTED_SOURCES.copy(),
            summary=None,
        )
