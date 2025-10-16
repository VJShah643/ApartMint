from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
DATA_BOSTAD = BASE_DIR / "bostad.json"
DATA_HEIMSTADEN = BASE_DIR / "heimstaden.json"


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


app = FastAPI(title="ApartMint", version="0.1.0")


# In-memory listing cache
LISTINGS: List[Dict[str, Any]] = load_listings()


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/listings")
def get_listings(limit: int = 24) -> Dict[str, Any]:
    items = LISTINGS[: max(0, min(limit, 100))]
    return {"count": len(items), "items": items}


@app.post("/api/chat")
async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    message = (body.get("message") or "").strip()
    prefs = extract_prefs(message)

    # Score and pick top matches
    scored: List[Tuple[int, Dict[str, Any]]] = [
        (score_listing(l, prefs), l) for l in LISTINGS
    ]
    # Filter to those with non-zero score first; fallback to top by images
    positives = [l for s, l in scored if s > 0]
    results = positives[:6] if positives else [l for _, l in scored][:6]

    reply_parts = []
    if prefs.get("city"):
        reply_parts.append(f"Looking around {prefs['city']}")
    if prefs.get("rooms"):
        reply_parts.append(f"with at least {prefs['rooms']} rooms")
    if prefs.get("budget"):
        reply_parts.append(f"under {prefs['budget']:,} kr")
    reply = (
        "I found some options "
        + (" ".join(reply_parts) if reply_parts else "you might like")
        + "."
    )

    return JSONResponse({
        "reply": reply,
        "preferences": prefs,
        "results": results,
    })


# Static files and SPA index
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")
