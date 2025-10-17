# ApartMint

ApartMint is a smart apartment-hunting chatbot that helps users find homes through natural conversation. It understands preferences like city, budget, rooms, and areas, and recommends matching listings — making apartment searching smooth and refreshingly minty 🍃.

## Current status (Oct 2025)

- Backend: FastAPI app serving a chat API and a small SPA (static HTML/JS/CSS).
- Data: Uses pre-scraped JSON datasets (`bostad.json`, `heimstaden.json`). The server auto-reloads data whenever these files change — ideal for a twice‑daily scraping job.
- LLM parsing: Google Gemini parses user messages into a structured SearchQuery (city, areas, minRooms, maxRooms, maxRent, keywords, sources) with a robust heuristic fallback.
- Session memory: Per-session preference memory with TTL, so you can refine queries across turns (e.g., set city first, then add rooms and budget later) without repeating context.
- Filtering & ranking: Strict filters (city, minRooms, maxRooms, maxRent, areas/keywords) applied to the cached listings, then ranked by fit.
- Front-end: Chat pane + recommendation cards. Shows basic preference summary, supports a “New search” reset.

What’s not in this repo: scrapers. The expected flow is that an external scraper writes/upserts to the JSON files twice per day.

## Project structure

- `main.py` – FastAPI app: endpoints, loading/normalizing listings, filtering/ranking, static site.
- `schemas.py` – Pydantic models, especially `SearchQuery`.
- `llm_client.py` – Gemini client + deterministic JSON extraction of `SearchQuery` with heuristic fallback.
- `session_store.py` – In-memory session preferences with TTL + merge rules.
- `translate_and_store.py` – Selective translation helpers (`*_en` fields) and JSON upsert utility.
- `clean.py` – Standalone cleaner/translator for bulk JSON processing (optional).
- `static/` – Minimal UI (`index.html`, `app.js`, `styles.css`).
- `bostad.json`, `heimstaden.json` – Current datasets (overwritten/updated by your scraping jobs).

## Setup

Requirements:
- Python 3.10+
- A Google Gemini API key in `.env` as `GEMINI_API_KEY=...`

Install and run:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open: http://127.0.0.1:8000/

Noise reduction (optional):

```bash
export GLOG_minloglevel=2
export GRPC_VERBOSITY=ERROR
uvicorn main:app --reload
```

## API

### GET /api/health
Health check.

### GET /api/listings?limit=24
Returns the first N normalized listings from the in-memory cache. The server will auto‑reload if `bostad.json` / `heimstaden.json` changed since last load.

### POST /api/chat
Parse a message into preferences, merge with session memory, filter/rank the cached database, and return results.

Request body:
```json
{
	"message": "Uppsala under 9000, exactly 2 rooms",
	"sessionId": "<client-stable-uuid>",
	"reset": false
}
```

Response (abbrev):
```json
{
	"reply": "I found some options Looking around Uppsala with at most 2 rooms under 9,000 kr.",
	"preferences": {
		"city": "Uppsala",
		"rooms": 2,
		"maxRooms": 2,
		"budget": 9000,
		"areas": ["Luthagen"],
		"keywords": [],
		"sources": ["heimstaden", "bostad"]
	},
	"results": [ { /* normalized listing */ } ]
}
```

### POST /api/reload
Force a manual reload from JSON files (useful right after scrape jobs finish). The server otherwise auto‑reloads on the next request when it detects file changes.

## Daily scrape workflow (recommended)

1) Your scrapers run twice a day and write to the project root:
	 - `bostad.json` (Uppsala Bostadsförmedling)
	 - `heimstaden.json` (Heimstaden)
2) Prefer upsert semantics and dedupe by `url`. Keep the shapes consistent with existing examples.
3) Optionally run selective translation during/after scrape using `translate_and_store.py` (adds `*_en` fields and timestamps).
4) The FastAPI server will pick up changes automatically on the next request, or call `POST /api/reload`.

Tip: a cron or GitHub Actions workflow can fetch and atomically replace the JSON files to avoid partial reads.

## Data model (normalized)

Each listing is normalized to include: `source`, `url`, `title`, `city`, `area`, `rent` + `rentNumeric`, `rooms` + `roomsNumeric`, `size` + `sizeNumeric`, `moveIn`, `landlord`, `images`.

## Session memory (preferences across turns)

- The front-end keeps a stable `sessionId` (localStorage) and sends it with each chat request.
- The server stores and merges structured preferences (no raw messages) for ~60 minutes of inactivity.
- Users can click “New search” (or send `reset`) to clear session state.

## Future work

Short-term:
- Range detection:
	- Rooms: parse "2–3" / "2 to 3" → `minRooms=2`, `maxRooms=3`.
	- Price range: parse "10–12k" → `minRent=10000`, `maxRent=12000` (requires adding `minRent`).
- Move‑in date filtering:
	- Parse Swedish/English dates, compare to `moveIn`/`available_from` across sources.
- UI chips for active filters with one‑click clears (city/rooms/budget/areas).

Medium-term:
- Scraper integration guide & adapters (function or HTTP interfaces) with retries/rate limits.
- Optional on‑demand scrape fallback when cache is empty for a city.
- Better dedup across sources (same address/size).
- Result explanations ("under budget by 500 kr", "in Uppsala, Rosendal").
- Tests: unit tests for parsing, merging, filtering, and normalization.

Longer-term:
- Docker/Compose for reproducible deployment.
- Background job runner (e.g., APScheduler/Celery) for scheduled scrapes and translations.
- LLM re‑ranking of top candidates using richer text (still respecting privacy and cost).

## Troubleshooting

- Seeing the same results after a scrape? Ensure your job wrote to `bostad.json` / `heimstaden.json`. The server auto‑reloads on the next request; you can also `POST /api/reload`.
- Chat replies generic? The LLM will fall back to heuristics if it can’t parse; try being explicit (city, rooms, budget). Also verify `GEMINI_API_KEY` is set.
- gRPC/absl warnings (harmless): silence by exporting `GLOG_minloglevel=2` and `GRPC_VERBOSITY=ERROR` before running the server.


## Quickstart

This repo now includes a simple web app (no database, no login): a split view with chat on the left and listing cards on the right. The backend is FastAPI and serves static files.

Requirements: Python 3.13

1) Install dependencies in your active venv

```
pip install -r requirements.txt
```

2) Run the dev server

```
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

3) Open in your browser

```
http://localhost:8000/
```

Data sources used for demo results are in `bostad.json` and `heimstaden.json`. The chat endpoint heuristically parses budget, rooms and city names from your message to filter and rank listings, and returns cards with images and links.

