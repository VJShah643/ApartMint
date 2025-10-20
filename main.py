from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
DATA_BOSTAD = BASE_DIR / "bostad.json"
DATA_HEIMSTADEN = BASE_DIR / "heimstaden.json"

# LLM + schemas
from schemas import SearchQuery, SUPPORTED_SOURCES
from llm_client import parse_search_query
from session_store import SessionStore
from intent_classifier import classify_intent
from conversational import (
    summarize_listing_with_llm,
    summarize_results_with_llm,
    generate_greeting_with_llm,
    generate_help_with_llm,
    generate_advisor_response,
)


def _to_int(value: Optional[str]) -> Optional[int]:
    if not value or not isinstance(value, str):
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _to_float(value: Optional[str]) -> Optional[float]:
    if not value or not isinstance(value, str):
        return None
    # Replace comma decimal separators, keep digits and dot/comma
    cleaned = value.replace(",", ".")
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    return float(m.group(1)) if m else None


def _first_int(value: Optional[str]) -> Optional[int]:
    if not value or not isinstance(value, str):
        return None
    m = re.search(r"(\d+)", value)
    return int(m.group(1)) if m else None


def normalize_bostad(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Skip empty/invalid rows
    if not isinstance(item, dict) or not item.get("url"):
        return None
    meaningful = any(
        item.get(k) not in (None, "", [], {})
        for k in item.keys() - {"url"}
    )
    if not meaningful:
        return None
    area = (item.get("area") or "").strip()
    city = None
    if area:
        city = area.split(",")[0].strip()
    rent_num = _to_int(item.get("rent"))
    rooms_num = _first_int(item.get("rooms"))
    size_num = _to_float(item.get("size"))
    images = item.get("images") or []
    title = item.get("title") or (area if area else "Listing")
    description = item.get("description") or ""
    return {
        "source": "bostad",
        "url": item.get("url"),
        "title": title,
        "city": city,
        "area": area,
        "rent": item.get("rent"),
        "rentNumeric": rent_num,
        "rooms": item.get("rooms"),
        "roomsNumeric": rooms_num,
        "size": item.get("size"),
        "sizeNumeric": size_num,
        "moveIn": item.get("move_in_date"),
        "landlord": item.get("landlord"),
        "description": description,
        "images": images,
    }


def normalize_heimstaden(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict) or not item.get("url"):
        return None
    meaningful = any(
        item.get(k) not in (None, "", [], {})
        for k in item.keys() - {"url"}
    )
    if not meaningful:
        return None
    location = (item.get("location") or "").strip()
    city = None
    if location and " - " in location:
        city = location.split(" - ")[0].strip()
    rent_num = _to_int(item.get("rent"))
    rooms_num = _first_int(item.get("rooms"))
    size_num = _to_float(item.get("size"))
    images = item.get("images") or []
    title = item.get("address") or (location if location else "Listing")
    description = item.get("description") or ""
    facilities = item.get("facilities") or []
    return {
        "source": "heimstaden",
        "url": item.get("url"),
        "title": title,
        "city": city,
        "area": location,
        "rent": item.get("rent"),
        "rentNumeric": rent_num,
        "rooms": item.get("rooms"),
        "roomsNumeric": rooms_num,
        "size": item.get("size"),
        "sizeNumeric": size_num,
        "moveIn": item.get("available_from"),
        "landlord": None,
        "description": description,
        "facilities": facilities,
        "images": images,
    }


def load_listings() -> List[Dict[str, Any]]:
    listings: List[Dict[str, Any]] = []
    # Bostad
    if DATA_BOSTAD.exists():
        try:
            bostad = json.loads(DATA_BOSTAD.read_text(encoding="utf-8"))
            for row in bostad:
                norm = normalize_bostad(row)
                if norm:
                    listings.append(norm)
        except Exception:
            pass
    # Heimstaden
    if DATA_HEIMSTADEN.exists():
        try:
            heim = json.loads(DATA_HEIMSTADEN.read_text(encoding="utf-8"))
            for row in heim:
                if row is None:
                    continue
                norm = normalize_heimstaden(row)
                if norm:
                    listings.append(norm)
        except Exception:
            pass
    return listings


def extract_prefs(message: str) -> Dict[str, Any]:
    # Very light heuristics to demo filtering
    budget = None
    rooms = None
    city = None

    # Budget: look for numbers optionally followed by kr or k
    m = re.search(r"(\d{4,6})\s*(?:kr|sek|:-)?", message, flags=re.I)
    if m:
        budget = int(m.group(1))

    # Rooms: look for '1 room', '2 rum', '3r', '4 rooms'
    m = re.search(r"(\d)\s*(?:rum|rooms?|br|r)\b", message, flags=re.I)
    if m:
        rooms = int(m.group(1))
    else:
        m = re.search(r"\b(?:1|2|3|4|5)\s*bed\b", message, flags=re.I)
        if m:
            rooms = int(re.search(r"\d", m.group(0)).group(0))

    # City: take a capitalized word or after 'in <city>'
    m = re.search(r"\bin\s+([A-ZÄÖÅ][a-zA-ZäöåÄÖÅ\-]+)", message)
    if m:
        city = m.group(1)
    else:
        tokens = re.findall(r"[A-ZÄÖÅ][a-zA-ZäöåÄÖÅ\-]+", message)
        if tokens:
            city = tokens[0]

    return {"budget": budget, "rooms": rooms, "city": city}


def score_listing(l: Dict[str, Any], prefs: Dict[str, Any]) -> int:
    score = 0
    budget = prefs.get("budget")
    rooms = prefs.get("rooms")
    city = prefs.get("city")
    if budget:
        rn = l.get("rentNumeric")
        if rn is not None:
            if rn <= budget:
                score += 5
            else:
                # small penalty if over budget
                over = rn - budget
                if over < 1000:
                    score += 2
                elif over < 3000:
                    score += 1
    if rooms:
        r = l.get("roomsNumeric")
        if r is not None and r >= rooms:
            score += 3
    if city:
        for field in (l.get("city") or "", l.get("area") or ""):
            if city.lower() in field.lower():
                score += 4
                break
    # Prefer those with images
    if l.get("images"):
        score += 1
    return score


app = FastAPI(title="ApartMint", version="0.1.0")


# In-memory listing cache
LISTINGS: List[Dict[str, Any]] = []
FILE_MTIMES: Dict[str, float] = {}


def _get_file_mtimes() -> Dict[str, float]:
    mt: Dict[str, float] = {}
    for p in (DATA_BOSTAD, DATA_HEIMSTADEN):
        if p.exists():
            try:
                mt[str(p)] = p.stat().st_mtime
            except Exception:
                pass
    return mt


def _reload_cache() -> None:
    global LISTINGS, FILE_MTIMES
    LISTINGS = load_listings()
    FILE_MTIMES = _get_file_mtimes()


def _reload_if_changed() -> None:
    current = _get_file_mtimes()
    if current != FILE_MTIMES:
        _reload_cache()


_reload_cache()
SESSIONS = SessionStore(ttl_minutes=60)


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/listings")
def get_listings(limit: int = 24) -> Dict[str, Any]:
    _reload_if_changed()
    items = LISTINGS[: max(0, min(limit, 100))]
    return {"count": len(items), "items": items}


@app.post("/api/chat")
async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    message = (body.get("message") or "").strip()
    session_id = (body.get("sessionId") or body.get("session_id") or "").strip()
    reset = bool(body.get("reset"))
    # Build supported cities from current dataset
    _reload_if_changed()
    all_listings = LISTINGS or load_listings()
    cities = sorted({(l.get("city") or "").strip() for l in all_listings if l.get("city")})

    # Handle session reset
    if reset and session_id:
        SESSIONS.reset(session_id)

    # Check current mode
    current_mode = SESSIONS.get_mode(session_id) if session_id else "broker"
    
    # If in advisor mode, route to advisor response
    if current_mode == "advisor":
        # Get conversation history for context (optional - you can implement this if needed)
        conversation_history = []  # You could track this in session if desired
        
        # Get last broker search results to provide context to advisor
        broker_listings = SESSIONS.get_last_results(session_id) if session_id else []
        
        advisor_result = generate_advisor_response(
            user_question=message,
            conversation_history=conversation_history,
            broker_listings=broker_listings
        )
        
        # Return empty results - frontend will keep existing cards visible in advisor mode
        return JSONResponse({
            "reply": advisor_result['response'],
            "preferences": {},
            "results": [],  # Frontend handles keeping cards visible
            "mode": "advisor",
            "sources": advisor_result.get('sources', []),
            "suggested_questions": advisor_result.get('suggested_questions', [])
        })

    # Get current conversation context
    conversation_context = SESSIONS.get_conversation_context(session_id) if session_id else ""

    # Classify intent with conversation context
    intent, context = classify_intent(message, conversation_context)

    # Handle greeting
    if intent == "greeting":
        greeting_reply = generate_greeting_with_llm(message)
        return JSONResponse({
            "reply": greeting_reply,
            "preferences": {},
            "results": []
        })

    # Handle help
    if intent == "help":
        help_reply = generate_help_with_llm()
        return JSONResponse({
            "reply": help_reply,
            "preferences": {},
            "results": []
        })

    # Handle detail request
    if intent == "detail" and session_id:
        # Special case: "show me again" or similar should show full list, not single listing
        msg_lower = message.lower().strip()
        show_list_patterns = [
            r"^show\s+(me\s+)?(them\s+)?(again|all|list|the\s+list)",
            r"^(see|view|display)\s+(them|all|the\s+list)",
            r"^list(\s+them|\s+all)?(\s+again)?$",
            r"^show\s+results",
        ]
        import re
        should_show_full_list = any(re.search(pat, msg_lower) for pat in show_list_patterns)
        
        if should_show_full_list:
            # User wants to see the full list of previous results
            last_results = SESSIONS.get_last_results(session_id)
            if last_results:
                result_summary = summarize_results_with_llm(last_results, SESSIONS.get(session_id))
                return JSONResponse({
                    "reply": result_summary,
                    "preferences": {},
                    "results": last_results  # Return full list
                })
            else:
                return JSONResponse({
                    "reply": "I don't have any previous search results. Try searching for apartments first!",
                    "preferences": {},
                    "results": []
                })
        
        # Check if this is a follow-up about the current listing
        current_listing = SESSIONS.get_current_listing(session_id)
        conversation_context = SESSIONS.get_conversation_context(session_id)
        
        # If we're in "discussing_listing" context, prefer to stay on current listing
        # unless user explicitly asks for a different one (e.g., "tell me about the third one")
        if conversation_context == "discussing_listing" and current_listing:
            # Check if user is explicitly asking for a DIFFERENT listing
            ctx_lower = (context or "").lower()
            is_explicit_switch = False
            
            # Ordinal positions indicate switching listings
            import re
            ordinal_patterns = [
                r'\b(first|second|third|fourth|fifth|sixth|1st|2nd|3rd|4th|5th|6th|\d+)\s*(listing|one|apartment)',
                r'\b(the\s+)?(first|second|third|1st|2nd|3rd)\b'
            ]
            for pattern in ordinal_patterns:
                if re.search(pattern, ctx_lower):
                    is_explicit_switch = True
                    break
            
            # Also check if they mention a specific different address/title
            if not is_explicit_switch and ctx_lower and len(ctx_lower) > 3:
                current_title = (current_listing.get("title") or "").lower()
                # If the context doesn't match current listing title, they might be switching
                if ctx_lower not in current_title and current_title not in ctx_lower:
                    # But only switch if it matches another listing
                    last_results = SESSIONS.get_last_results(session_id)
                    for item in last_results:
                        if item == current_listing:
                            continue  # Skip current listing
                        title = (item.get("title") or "").lower()
                        area = (item.get("area") or "").lower()
                        if ctx_lower in title or ctx_lower in area:
                            is_explicit_switch = True
                            break
            
            if not is_explicit_switch:
                # Stay on current listing - this is a follow-up question
                listing = current_listing
            else:
                # User wants to switch to a different listing
                listing = None
        else:
            # Not in conversation context, or no current listing
            listing = None
        
        # If we don't have a listing yet, find it from last results
        if not listing:
            last_results = SESSIONS.get_last_results(session_id)
            if not last_results:
                return JSONResponse({
                    "reply": "I don't have any recent listings to reference. Try searching first, then ask me about a specific one!",
                    "preferences": {},
                    "results": []
                })
            
            # Try to find the listing by context (title, position, etc.)
            ctx_lower = (context or "").lower()
            
            # Check for ordinal position: "first", "second", "third", "1st", "2nd", or digit
            import re
            ordinal_map = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
                           "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6}
            for word, idx in ordinal_map.items():
                if word in ctx_lower:
                    if idx <= len(last_results):
                        listing = last_results[idx - 1]
                    break
            # Or plain digit
            if not listing:
                m = re.search(r'\b(\d+)\b', ctx_lower)
                if m:
                    idx = int(m.group(1))
                    if 1 <= idx <= len(last_results):
                        listing = last_results[idx - 1]
            
            # Or match by title/address substring
            if not listing and ctx_lower:
                for item in last_results:
                    title = (item.get("title") or "").lower()
                    area = (item.get("area") or "").lower()
                    if ctx_lower in title or ctx_lower in area:
                        listing = item
                        break
            
            if not listing and last_results:
                # Default to first if ambiguous
                listing = last_results[0]
        
        if listing:
            # Store this as the current listing we're discussing
            SESSIONS.set_current_listing(session_id, listing)
            SESSIONS.set_conversation_context(session_id, "discussing_listing")
            
            summary = summarize_listing_with_llm(listing, user_question=message)
            return JSONResponse({
                "reply": summary,
                "preferences": {},
                "results": [listing]  # show just this one
            })
        else:
            return JSONResponse({
                "reply": "I couldn't find that listing in your recent results. Could you be more specific or search again?",
                "preferences": {},
                "results": []
            })

    # Default: search intent
    # Try LLM-based structured parsing, fallback to heuristic (partial update)
    sq_partial: SearchQuery = parse_search_query(message, supported_cities=cities)

    # Merge with session preferences if session_id provided
    if session_id:
        sq = SESSIONS.merge(session_id, sq_partial)
    else:
        sq = sq_partial

    # Map SearchQuery to existing scoring preferences
    prefs = {"budget": sq.maxRent, "rooms": sq.minRooms, "maxRooms": sq.maxRooms, "city": sq.city}

    # Filter strictly by constraints from SearchQuery, then rank
    def passes_filters(l: Dict[str, Any]) -> bool:
        # City filter
        if sq.city:
            hay = " ".join([(l.get("city") or ""), (l.get("area") or "")]).lower()
            if sq.city.lower() not in hay:
                return False
        # Areas (any)
        if sq.areas:
            area_text = " ".join([(l.get("area") or ""), (l.get("title") or "")]).lower()
            if not any(a.lower() in area_text for a in sq.areas if a):
                return False
        # Rooms lower/upper bounds
        rn = l.get("roomsNumeric")
        if sq.minRooms is not None:
            if rn is None or rn < sq.minRooms:
                return False
        if sq.maxRooms is not None:
            if rn is None or rn > sq.maxRooms:
                return False
        # Rent
        if sq.maxRent is not None:
            rent = l.get("rentNumeric")
            if rent is None or rent > sq.maxRent:
                return False
        # Keywords (any)
        if sq.keywords:
            text = " ".join(
                [
                    str(l.get("title") or ""),
                    str(l.get("area") or ""),
                    str(l.get("city") or ""),
                ]
            ).lower()
            if not any(k.lower() in text for k in sq.keywords if k):
                return False
        return True

    filtered = [l for l in LISTINGS if passes_filters(l)]

    def rank_key(l: Dict[str, Any]) -> Tuple[int, int, int]:
        # Higher is better; build on top of existing score heuristic
        s = score_listing(l, prefs)
        # Prefer closer to budget (if provided)
        closeness = 0
        if sq.maxRent and l.get("rentNumeric") is not None:
            diff = sq.maxRent - int(l["rentNumeric"])  # positive if under budget
            # cap influence
            closeness = max(-5000, min(5000, diff))
        # Prefer more rooms
        rooms_num = l.get("roomsNumeric") or 0
        return (s, closeness, rooms_num)

    results: List[Dict[str, Any]]
    if filtered:
        results = sorted(filtered, key=rank_key, reverse=True)[:6]
    else:
        # fallback to best overall
        scored: List[Tuple[int, Dict[str, Any]]] = [
            (score_listing(l, prefs), l) for l in LISTINGS
        ]
        results = [l for _, l in sorted(scored, key=lambda t: t[0], reverse=True)[:6]]

    # Store last results in session for detail queries
    if session_id and results:
        SESSIONS.set_last_results(session_id, results)
        # Reset conversation context - we're showing new search results now
        SESSIONS.set_conversation_context(session_id, "")
        SESSIONS.set_current_listing(session_id, None)

    # Generate conversational result summary using LLM
    result_summary = summarize_results_with_llm(results, prefs)

    # Attach LLM summary if available
    return JSONResponse(
        {
            "reply": result_summary,
            "preferences": {
                "budget": prefs.get("budget"),
                "rooms": prefs.get("rooms"),
                "maxRooms": prefs.get("maxRooms"),
                "city": prefs.get("city"),
                "areas": sq.areas,
                "keywords": sq.keywords,
                "sources": sq.sources or SUPPORTED_SOURCES,
            },
            "results": results,
        }
    )


@app.post("/api/reload")
def reload_endpoint() -> Dict[str, Any]:
    """Manually reload listings from JSON files (useful after scrapes)."""
    _reload_cache()
    return {"status": "reloaded", "count": len(LISTINGS)}


@app.post("/api/reset")
def reset_session(request: Request) -> Dict[str, Any]:
    """Reset preferences for a given sessionId. Body: { sessionId: string }"""
    try:
        import asyncio
        # FastAPI allows await request.json() in async paths; here just support sync
        # but if this runs under ASGI, it will still work.
    except Exception:
        pass
    # Using Request.json() requires async; read from body via starlette if desired.
    # To keep simple, let /api/chat handle reset flag primarily.
    return {"status": "ok"}


@app.post("/api/switch_mode")
async def switch_mode(request: Request) -> JSONResponse:
    """Switch between broker and advisor modes.
    Body: { sessionId: string, mode: 'broker' | 'advisor' }
    """
    body = await request.json()
    session_id = (body.get("sessionId") or body.get("session_id") or "").strip()
    mode = (body.get("mode") or "broker").strip().lower()
    
    if mode not in ["broker", "advisor"]:
        return JSONResponse({
            "status": "error",
            "message": "Invalid mode. Must be 'broker' or 'advisor'."
        }, status_code=400)
    
    if not session_id:
        return JSONResponse({
            "status": "error",
            "message": "sessionId is required."
        }, status_code=400)
    
    # Set the mode in session
    SESSIONS.set_mode(session_id, mode)
    
    # Clear conversation context when switching modes
    # This prevents confusion between advisor discussions and broker searches
    if mode == "broker":
        SESSIONS.set_conversation_context(session_id, "")
        SESSIONS.set_current_listing(session_id, None)
    
    # Generate appropriate response
    if mode == "advisor":
        reply = (
            "🎓 **Advisor Mode activated!** I'm here to guide you through Sweden's rental housing market.\n\n"
            "I can help you understand:\n"
            "- How Bostadsförmedling queue systems work (Uppsala, Stockholm, etc.)\n"
            "- Student housing options and strategies\n"
            "- Budget planning and cost breakdowns\n"
            "- Neighborhood comparisons and area insights\n"
            "- Application tips and success strategies\n\n"
            "Ask me anything about finding housing in Sweden! (I won't search apartments in this mode - "
            "switch to Broker Mode for that)"
        )
    else:
        reply = (
            "🔍 **Broker Mode activated!** I'm ready to search for apartments.\n\n"
            "Tell me what you're looking for:\n"
            "- City (e.g., Uppsala, Stockholm)\n"
            "- Budget (e.g., under 8000 kr/month)\n"
            "- Number of rooms (e.g., 2 rooms, at least 3 rooms)\n"
            "- Neighborhood (e.g., Luthagen, Södermalm)\n\n"
            "I'll find the best matches for you!"
        )
    
    return JSONResponse({
        "status": "success",
        "mode": mode,
        "reply": reply
    })


# Static files and SPA index
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
