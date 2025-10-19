from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from pydantic import ValidationError
from schemas import SearchQuery, SUPPORTED_SOURCES

load_dotenv()


class LLMUnavailable(Exception):
    pass



# Gemini client setup
def _get_gemini_client():
    """Return a configured Gemini client instance."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
    if not api_key:
        raise LLMUnavailable("Missing GEMINI_API_KEY in environment")
    try:
        import google.generativeai as genai  # type: ignore
    except Exception as e:
        raise LLMUnavailable(f"Gemini SDK not installed: {e}")
    genai.configure(api_key=api_key)
    return genai


# Initialize the Gemini model
_genai = _get_gemini_client()
_MODEL = _genai.GenerativeModel("gemini-2.5-flash")


# Store chat sessions (one per user)

_CHAT_SESSIONS: Dict[str, Any] = {}


def get_chat_session(session_id: str):
    """Return a persistent Gemini chat for a given session_id."""
    if not session_id:
        session_id = "default"
    if session_id not in _CHAT_SESSIONS:
        # Start a new chat with empty history
        _CHAT_SESSIONS[session_id] = _MODEL.start_chat(history=[])
    return _CHAT_SESSIONS[session_id]



# Parsing user query (structured JSON)

SYS_PROMPT = (
    "You are a strict JSON API. Extract structured apartment search preferences from the user message. "
    "Return ONLY a JSON object with fields: city (string|null), areas (string[]), minRooms (int|null), "
    "maxRooms (int|null), maxRent (int|null), keywords (string[]), sources (string[] from ['heimstaden','bostad']), "
    "summary (string). "
    "Cities and areas should be capitalized as proper nouns. Prices are monthly SEK if unspecified. Rooms are integer count. "
    "Interpret phrases like 'at least 2 rooms' -> minRooms=2; 'at most 2 rooms' -> maxRooms=2. "
    "If unsure, leave fields null or empty."
)


def parse_search_query(message: str, supported_cities: List[str], session_id: Optional[str] = None) -> SearchQuery:
    """Use the persistent Gemini chat to parse user query."""
    chat = get_chat_session(session_id or "default")

    prompt = (
        f"System: {SYS_PROMPT}\n\n"
        f"Supported cities: {supported_cities}. Supported sources: {SUPPORTED_SOURCES}.\n"
        f"User: {message}\nReturn JSON only."
    )

    try:
        resp = chat.send_message(prompt)
        text = resp.text
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            text = text.replace("json", "", 1).strip()

        data = json.loads(text)
        sq = SearchQuery(**data)
        if not sq.sources:
            sq.sources = SUPPORTED_SOURCES.copy()
        return sq

    except Exception as e:
        print("LLM parsing failed, falling back to heuristic:", e)
        # fallback same as before (regex)
        import re
        budget = None
        min_rooms = None
        max_rooms = None
        city = None
        m = re.search(r"(\d{4,6})\s*(?:kr|sek|:-|/mo|per\s*month)?", message, flags=re.I)
        if m:
            budget = int(m.group(1))
        m = re.search(r"(?:at\s*most|<=|max)\s*(\d)\s*(?:rum|rooms?|br|r|bed)\b", message, flags=re.I)
        if m:
            max_rooms = int(m.group(1))
        m = re.search(r"(?:at\s*least|>=|min)\s*(\d)\s*(?:rum|rooms?|br|r|bed)\b", message, flags=re.I)
        if m:
            min_rooms = int(m.group(1))
        if min_rooms is None and max_rooms is None:
            m = re.search(r"(\d)\s*(?:rum|rooms?|br|r|bed)\b", message, flags=re.I)
            if m:
                min_rooms = int(m.group(1))
        for c in supported_cities:
            if re.search(rf"\b{re.escape(c)}\b", message, flags=re.I):
                city = c
                break
        keywords = []
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



# Summarize listings (using same chat)

def generate_summary_with_llm(user_query: str, listings: List[Dict[str, Any]], session_id: Optional[str] = None) -> Optional[str]:
    """Summarize listings while sharing chat memory."""
    chat = get_chat_session(session_id or "default")

    # turn listings into short text
    context_text = "\n".join(
        [f"{l.get('title')} – {l.get('rooms')}, {l.get('rent')}, {l.get('city')}" for l in listings[:6]]
    )

    prompt = (
        "You are a helpful real estate assistant. "
        "Based on the previous conversation and the following listings, "
        "write a short summary that answers the user's query "
        "and highlights price ranges, locations, and room counts.\n\n"
        f"User query: {user_query}\n\nListings:\n{context_text}\n\nSummary:"
    )

    try:
        resp = chat.send_message(prompt)
        summary = resp.text.strip()
        return summary
    except Exception as e:
        print("Summary generation failed:", e)
        return None
def generate_answer_from_context(user_query: str, context_text: str, session_id: Optional[str] = None) -> Optional[str]:
    """
    Use retrieved RAG context (for example, 'how to apply' info) to answer the user's question.
    Shares the same persistent Gemini chat session.
    The model should only rely on the given context when answering.
    """
    chat = get_chat_session(session_id or "default")

    prompt = (
        "You are a helpful real estate assistant. "
        "Answer the user's question using ONLY the information provided in the context on how to apply to heimstaden or bostad.se apartments. "
        "If the answer is not contained in the context, say poloitely that you don't know and suggest the user visit the official website for more information and also mention what kind of information you provide here "
        "Do not invent or assume details.\n\n"
        f"Context:\n{context_text}\n\n"
        f"User question:\n{user_query}\n\n"
        "Answer clearly and naturally:"
    )

    try:
        resp = chat.send_message(prompt)
        answer = resp.text.strip()
        return answer
    except Exception as e:
        print("Context-based answering failed:", e)
        return None
