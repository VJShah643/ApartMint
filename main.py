from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# LLM + schemas
from schemas import SearchQuery, SUPPORTED_SOURCES
from llm_client import generate_summary_with_llm, parse_search_query, generate_answer_from_context
from session_store import SessionStore
import faiss
import pickle
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parent
DATA_BOSTAD = BASE_DIR / "bostad.json"
DATA_HEIMSTADEN = BASE_DIR / "heimstaden.json"



RAG_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
RAG_INDEX = faiss.read_index("apply_info.index")
with open("apply_info_meta.pkl", "rb") as f:
    RAG_META = pickle.load(f)

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

def rag_search_apply_info(query: str, top_k: int = 2):
    """
    Search the FAISS index for relevant 'how to apply' information.
    Only triggers if the query is about applying or registration.
    """
    keywords = ["apply", "application", "queue", "register", "sign up", "process"]
    if not any(word in query.lower() for word in keywords):
        return None

    q_emb = RAG_MODEL.encode([query])
    distances, indices = RAG_INDEX.search(q_emb, top_k)
    if not len(indices):
        return None

    results = [RAG_META[i]["text"] for i in indices[0] if i != -1]
    if not results:
        return None

    return "\n".join(results)


app = FastAPI(title="ApartMint", version="0.1.0")


# In-memory listing cache
LISTINGS: List[Dict[str, Any]] = []
FILE_MTIMES: Dict[str, float] = {}

def summarize_listings_text(listings: List[Dict[str, Any]]) -> str:
    """Convert listings to short, readable text blocks for the LLM."""
    parts = []
    for l in listings[:6]:
        city = l.get("city") or ""
        title = l.get("title") or ""
        rent = l.get("rent") or ""
        rooms = l.get("rooms") or ""
        size = l.get("size") or ""
        parts.append(f"{title} – {rooms} rooms, {size}, rent {rent}, {city}")
    return "\n".join(parts)


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

    # Try LLM-based structured parsing, fallback to heuristic (partial update)
    sq_partial: SearchQuery = parse_search_query(message, supported_cities=cities, session_id=session_id)

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

    reply_parts = []
    if prefs.get("city"):
        reply_parts.append(f"Looking around {prefs['city']}")
    if prefs.get("rooms") and prefs.get("maxRooms"):
        reply_parts.append(f"with {prefs['rooms']}–{prefs['maxRooms']} rooms")
    elif prefs.get("rooms"):
        reply_parts.append(f"with at least {prefs['rooms']} rooms")
    elif prefs.get("maxRooms"):
        reply_parts.append(f"with at most {prefs['maxRooms']} rooms")
    if prefs.get("budget"):
        reply_parts.append(f"under {prefs['budget']:,} kr")
    reply = (
        "I found some options "
        + (" ".join(reply_parts) if reply_parts else "you might like")
        + "."
    )
    llm_summary = None
    # --- Check if the user asked about applying ---
    apply_info = rag_search_apply_info(message)
    if apply_info:
        llm_summary = generate_answer_from_context(message, apply_info, session_id=session_id)
    else:
        # Ask the LLM to summarize the top listings
        llm_summary = generate_summary_with_llm(message, results, session_id=session_id)
    
    if llm_summary:
        reply = llm_summary

    # Attach LLM summary if available
    return JSONResponse(
        {
            "reply": reply,
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


# Static files and SPA index
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
