from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional

from schemas import SearchQuery


def merge_queries(base: SearchQuery, update: SearchQuery) -> SearchQuery:
    """Merge two SearchQuery objects with simple override/union rules."""
    city = update.city or base.city
    # union areas/keywords; preserve order by preferring base then adding new
    areas = list(dict.fromkeys([*(base.areas or []), *([a for a in update.areas if a] or [])]))
    keywords = list(dict.fromkeys([*(base.keywords or []), *([k for k in update.keywords if k] or [])]))
    min_rooms = update.minRooms if update.minRooms is not None else base.minRooms
    max_rooms = update.maxRooms if update.maxRooms is not None else base.maxRooms
    max_rent = update.maxRent if update.maxRent is not None else base.maxRent
    sources = update.sources or base.sources
    summary = update.summary or base.summary

    return SearchQuery(
        city=city,
        areas=areas,
        minRooms=min_rooms,
        maxRooms=max_rooms,
        maxRent=max_rent,
        keywords=keywords,
        sources=sources,
        summary=summary,
    )


@dataclass
class SessionData:
    prefs: SearchQuery = field(default_factory=SearchQuery)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_results: list = field(default_factory=list)  # store last shown listings for detail queries
    current_listing: Optional[dict] = None  # track which listing user is currently discussing
    conversation_context: str = ""  # track what we're talking about
    current_mode: str = "broker"  # "broker" or "advisor" mode


class SessionStore:
    def __init__(self, ttl_minutes: int = 60) -> None:
        self._data: Dict[str, SessionData] = {}
        self._ttl = timedelta(minutes=ttl_minutes)

    def get(self, session_id: str) -> SearchQuery:
        sd = self._data.get(session_id)
        if not sd:
            return SearchQuery()
        # TTL check
        if datetime.utcnow() - sd.updated_at > self._ttl:
            self._data.pop(session_id, None)
            return SearchQuery()
        return sd.prefs

    def set(self, session_id: str, prefs: SearchQuery, last_results: list = None) -> None:
        sd = self._data.get(session_id, SessionData())
        sd.prefs = prefs
        sd.updated_at = datetime.utcnow()
        if last_results is not None:
            sd.last_results = last_results
        self._data[session_id] = sd

    def merge(self, session_id: str, update: SearchQuery) -> SearchQuery:
        current = self.get(session_id)
        merged = merge_queries(current, update)
        self.set(session_id, merged)
        return merged

    def get_last_results(self, session_id: str) -> list:
        sd = self._data.get(session_id)
        return sd.last_results if sd else []

    def set_last_results(self, session_id: str, results: list) -> None:
        sd = self._data.get(session_id)
        if sd:
            sd.last_results = results
            sd.updated_at = datetime.utcnow()

    def get_current_listing(self, session_id: str) -> Optional[dict]:
        """Get the listing currently being discussed."""
        sd = self._data.get(session_id)
        return sd.current_listing if sd else None

    def set_current_listing(self, session_id: str, listing: Optional[dict]) -> None:
        """Set the listing currently being discussed."""
        sd = self._data.get(session_id)
        if sd:
            sd.current_listing = listing
            sd.updated_at = datetime.utcnow()

    def get_conversation_context(self, session_id: str) -> str:
        """Get the current conversation context (e.g., 'discussing_listing', 'searching')."""
        sd = self._data.get(session_id)
        return sd.conversation_context if sd else ""

    def set_conversation_context(self, session_id: str, context: str) -> None:
        """Set the conversation context."""
        sd = self._data.get(session_id)
        if sd:
            sd.conversation_context = context
            sd.updated_at = datetime.utcnow()

    def get_mode(self, session_id: str) -> str:
        """Get the current mode ('broker' or 'advisor')."""
        sd = self._data.get(session_id)
        return sd.current_mode if sd else "broker"

    def set_mode(self, session_id: str, mode: str) -> None:
        """Set the current mode ('broker' or 'advisor')."""
        if mode not in ["broker", "advisor"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'broker' or 'advisor'.")
        sd = self._data.get(session_id, SessionData())
        sd.current_mode = mode
        sd.updated_at = datetime.utcnow()
        self._data[session_id] = sd

    def reset(self, session_id: str) -> None:
        self._data.pop(session_id, None)

    def cleanup(self) -> int:
        now = datetime.utcnow()
        keys = [k for k, v in self._data.items() if now - v.updated_at > self._ttl]
        for k in keys:
            self._data.pop(k, None)
        return len(keys)
