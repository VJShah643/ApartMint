# ApartMint

ApartMint is a conversational apartment-hunting assistant with **dual modes**:
1. **Broker Mode** 🔍: Search and filter apartments across Uppsala
2. **Advisor Mode** 🎓: Get expert guidance about Uppsala's housing market

It understands preferences like city, budget, rooms, and areas, remembers context across turns, and provides friendly, personalized recommendations — making apartment searching smooth and refreshingly minty 🍃.

## Current status (Oct 2025)

- **Dual-mode system**: Switch between apartment search (Broker) and housing consultation (Advisor)
- **RAG-powered Advisor**: 7 comprehensive knowledge base guides covering Uppsala housing
- **Backend**: FastAPI app serving a chat API and a modern SPA.
- **Data**: Uses pre-scraped JSON datasets (`bostad.json`, `heimstaden.json`). The server auto-reloads data whenever these files change — ideal for a twice‑daily scraping job.
- **LLM integration**: Google Gemini 2.0 Flash powers intelligent conversational features throughout the app.
- **Session memory**: Per-session preference memory with TTL, mode tracking, and conversation context.
- **Fully LLM-powered conversation**: Intent classification, greetings, help responses, query parsing, result summaries, listing details, and advisor responses all use Gemini 2.0.
- **Conversational UX**: 
  - Typing indicators (animated dots) while processing
  - Typewriter effect (character-by-character message display)
  - Personalized greetings and help responses
  - Natural language summaries of search results
  - Rich listing descriptions with full context sent to LLM
- **Filtering & ranking**: Strict filters (city, minRooms, maxRooms, maxRent, areas/keywords) applied to cached listings, then ranked by fit.
- **Front-end**: Chat pane with typing animations + recommendation cards showing images, rent, rooms, size, and description snippets.

**What's not in this repo**: scrapers. The expected flow is that an external scraper writes/upserts to the JSON files twice per day.

## Project structure

- `main.py` – FastAPI app: endpoints, loading/normalizing listings (preserves descriptions & facilities), intent routing, filtering/ranking, mode switching, static site.
- `schemas.py` – Pydantic models, especially `SearchQuery`.
- `llm_client.py` – Gemini 2.0 Flash client for query parsing with JSON extraction and regex fallback.
- `intent_classifier.py` – **LLM-powered** intent detection (greeting, help, detail, search) with regex fallback.
- `conversational.py` – **LLM-powered** greetings, help responses, listing summaries (full descriptions), result set intros, and **advisor responses with RAG**.
- `session_store.py` – In-memory session preferences + last_results tracking + current_mode + conversation context with TTL + merge rules.
- `rag_system.py` – **RAG system**: loads knowledge base markdown files, creates embeddings with sentence-transformers, retrieves relevant context with ChromaDB.
- `advisor_prompts.py` – System prompts and prompt builders for advisor mode with grounding rules.
- `knowledge_base/` – **7 comprehensive guides** (6,300+ lines total):
  - `bostad_process.md` – Uppsala Bostadsförmedling complete guide
  - `heimstaden_process.md` – Heimstaden application process
  - `queue_strategies.md` – Queue day optimization tactics
  - `student_housing.md` – Student housing options & strategies
  - `budget_planning.md` – Financial planning for renters
  - `area_comparisons.md` – Uppsala neighborhood guides
  - `application_tips.md` – Winning application strategies
- `translate_and_store.py` – Selective translation helpers (`*_en` fields) and JSON upsert utility.
- `clean.py` – Standalone cleaner/translator for bulk JSON processing (optional).
- `static/` – Minimal UI (`index.html`, `app.js` with typing effects, `styles.css`).
- `bostad.json`, `heimstaden.json` – Current datasets (overwritten/updated by your scraping jobs).

## Setup

**Requirements:**
- Python 3.10+
- A Google Gemini API key in `.env` as `GEMINI_API_KEY=...`

**Install and run:**

\`\`\`bash
pip install -r requirements.txt
uvicorn main:app --reload
\`\`\`

**Note**: The first request will initialize the RAG knowledge base (takes ~30 seconds to load embeddings). Subsequent requests will be fast.

**Open:** http://127.0.0.1:8000/

**Noise reduction (optional):**

\`\`\`bash
export GLOG_minloglevel=2
export GRPC_VERBOSITY=ERROR
uvicorn main:app --reload
\`\`\`

## API

### GET /api/health
Health check.

### GET /api/listings?limit=24
Returns the first N normalized listings from the in-memory cache. The server will auto‑reload if `bostad.json` / `heimstaden.json` changed since last load.

### POST /api/switch_mode
Switch between broker and advisor modes.

**Request body:**
\`\`\`json
{
  "sessionId": "<client-stable-uuid>",
  "mode": "advisor"  // or "broker"
}
\`\`\`

**Response:**
\`\`\`json
{
  "status": "success",
  "mode": "advisor",
  "reply": "🎓 Advisor Mode activated! I'm here to guide you through Uppsala's housing market..."
}
\`\`\`

### POST /api/chat
Main conversational endpoint. Uses LLM to classify intent, route to appropriate mode (broker or advisor), and generate natural responses.

**Request body:**
\`\`\`json
{
  "message": "hey, what can you do?",
  "sessionId": "<client-stable-uuid>",
  "reset": false
}
\`\`\`

**Response (greeting):**
\`\`\`json
{
  "reply": "Hey there! 👋 I'm ApartMint, your friendly apartment search assistant. I can help you find apartments across Sweden by city, budget, number of rooms, and neighborhoods. What are you looking for?",
  "preferences": {},
  "results": []
}
\`\`\`

**Response (help):**
\`\`\`json
{
  "reply": "I can help you search for apartments! Tell me:\n• City (Uppsala, Stockholm, etc.)\n• Budget (e.g., under 10000 kr)\n• Rooms (e.g., 2 rooms, at least 3)\n• Areas or keywords (balcony, student)\n\nI'll remember your preferences across messages. Ask 'tell me about the second listing' for details!",
  "preferences": {},
  "results": []
}
\`\`\`

**Response (search):**
\`\`\`json
{
  "reply": "I found 6 apartments in Uppsala with exactly 2 rooms under 9,000 kr/month. Most are available in November and December, ranging from 25-45m².",
  "preferences": {
    "city": "Uppsala",
    "minRooms": 2,
    "maxRooms": 2,
    "maxRent": 9000,
    "areas": [],
    "keywords": [],
    "sources": ["heimstaden", "bostad"]
  },
  "results": [ { /* normalized listing with full description */ } ]
}
\`\`\`

**Response (advisor mode):**
\`\`\`json
{
  "reply": "Great question! Uppsala Bostadsförmedling (Bostad Uppsala) uses a queue-based system...",
  "preferences": {},
  "results": [],
  "mode": "advisor",
  "sources": ["bostad_process.md", "queue_strategies.md"],
  "suggested_questions": [
    "How long does it take to get an apartment?",
    "Can I keep accumulating queue days while renting?",
    "What are the cheapest neighborhoods in Uppsala?"
  ]
}
\`\`\`

**Response (detail):**
\`\`\`json
{
  "reply": "Studentstaden 22 is a cozy 12m² room in Uppsala's Luthagen area, perfect for students. The apartment features a private sink and shared kitchen/bathroom facilities with 4 other tenants—great for social living! Monthly rent is 3,607 kr, and it's available starting January 2026. The building includes laundry facilities and bicycle storage.",
  "preferences": {},
  "results": [ { /* single listing with full details */ } ]
}
\`\`\`

### POST /api/reload
Force a manual reload from JSON files (useful right after scrape jobs finish). The server otherwise auto‑reloads on the next request when it detects file changes.

## LLM Integration

### Model: Google Gemini 2.0 Flash Experimental

All LLM interactions use `gemini-2.0-flash-exp` for optimal performance, accuracy, and speed.

### LLM-Powered Features

| **Feature** | **What LLM Does** | **Fallback** |
|-------------|-------------------|--------------|
| **Intent Classification** | Understands user intent from natural language (greeting, help, detail, search) | Regex pattern matching |
| **Greeting Responses** | Generates personalized, warm greetings based on user's message | Fixed template |
| **Help Responses** | Explains capabilities conversationally with examples | Formatted bullet points |
| **Query Parsing** | Extracts structured SearchQuery (city, rooms, budget, etc.) from free-form text | Regex extraction |
| **Result Summaries** | Creates 2-3 sentence natural intro to search results with insights | Template with count/filters |
| **Listing Details** | Generates 3-5 sentence rich summaries with **full description context** | Template with truncated description |
| **Advisor Responses** | **RAG-powered**: Retrieves relevant knowledge base context, generates grounded answers | Error message with suggestions |

### RAG System (Advisor Mode)

The advisor mode uses **Retrieval-Augmented Generation** to provide accurate, grounded responses:

1. **Knowledge Base**: 7 comprehensive markdown guides (6,300+ lines) covering Uppsala housing
2. **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` for semantic search
3. **Vector Store**: ChromaDB for efficient similarity search
4. **Retrieval**: Top 5 most relevant chunks retrieved per query
5. **Grounding**: LLM only uses retrieved context (no hallucination)
6. **Sources**: Responses cite which knowledge base files were consulted

**Knowledge Base Topics**:
- Uppsala Bostadsförmedling queue system & process
- Heimstaden application requirements & timeline
- Queue day optimization strategies
- Student housing options (Studentstaden, nations, etc.)
- Budget planning & cost breakdowns
- Uppsala area comparisons & neighborhood guides
- Application tips & success strategies

### LLM Calls Per Request Type

- **Greeting**: 2 calls (classify intent + generate greeting)
- **Help**: 2 calls (classify intent + generate help)
- **Search**: 3 calls (classify intent + parse query + summarize results)
- **Detail**: 2 calls (classify intent + summarize listing)

### Privacy & Cost Considerations

- Only structured data sent to LLM, never raw user messages stored
- Fallback mechanisms ensure app works even if LLM unavailable
- Intent classification happens first to route appropriately
- Session memory uses deterministic merging (no LLM needed)

## Daily scrape workflow (recommended)

1. Your scrapers run twice a day and write to the project root:
   - `bostad.json` (Uppsala Bostadsförmedling)
   - `heimstaden.json` (Heimstaden)
2. Prefer upsert semantics and dedupe by `url`. Keep the shapes consistent with existing examples.
3. Optionally run selective translation during/after scrape using `translate_and_store.py` (adds `*_en` fields and timestamps).
4. The FastAPI server will pick up changes automatically on the next request, or call `POST /api/reload`.

**Tip:** A cron job or GitHub Actions workflow can fetch and atomically replace the JSON files to avoid partial reads.

## Data model (normalized)

Each listing is normalized to include: `source`, `url`, `title`, `city`, `area`, `rent` + `rentNumeric`, `rooms` + `roomsNumeric`, `size` + `sizeNumeric`, `moveIn`, `landlord`, `description`, `facilities`, `images`.

**Descriptions** are preserved from source data and used for:
- **LLM-generated detail summaries** (full description sent to Gemini, no truncation)
- Card display snippets (first 120 chars shown in UI)
- Conversational context

## Conversational features

### Intent classification (LLM-powered)
- **Greeting** ("hey", "hello", "hi", "good morning") → personalized welcome message
- **Help** ("what can you do?", "how does this work?", "guide me") → conversational explanation of capabilities
- **Detail** ("tell me about the second listing", "more info on Studentstaden 22") → rich 3-5 sentence summary with full description
- **Search** (default) → apartment search with LLM-parsed preferences

### Natural language understanding (LLM-powered)
- "N rooms" (e.g., "2 rooms") → exactly N rooms (both minRooms and maxRooms set)
- "at least N rooms" → minRooms only
- "at most N rooms" → maxRooms only
- City names, budget amounts, and keywords extracted via Gemini with regex fallback
- Handles Swedish and English input

### LLM-powered responses
1. **Intent classification**: Gemini determines what the user wants
2. **Personalized greetings**: Warm, contextual welcome messages
3. **Conversational help**: Natural explanation of capabilities with examples
4. **Query parsing**: Gemini extracts structured SearchQuery from free-form text
5. **Result summaries**: "I found 6 apartments in Uppsala with exactly 2 rooms under 9,000 kr/month. Most are available in November..."
6. **Listing details**: Rich 3-5 sentence summaries including full description highlights, facilities, and key info

### UI/UX enhancements
- **Typing indicator**: Animated dots while bot is "thinking"
- **Typewriter effect**: Messages appear character-by-character (15ms/char)
- **Line breaks**: Preserved in help messages and multi-line responses via `white-space: pre-wrap`
- **Description snippets**: Cards show first 120 chars of listing description
- **"New search" button**: Clears session memory to start fresh

## Session memory (preferences across turns)

- The front-end keeps a stable `sessionId` (localStorage) and sends it with each chat request.
- The server stores and merges structured preferences (no raw messages) for ~60 minutes of inactivity.
- Also tracks `last_results` to enable detail queries like "tell me more about the first listing."
- Users can click "New search" (or send `reset`) to clear session state.

## Future work

**Short-term:**
- Range detection:
  - Rooms: parse "2–3" / "2 to 3" → `minRooms=2`, `maxRooms=3`.
  - Price range: parse "10–12k" → `minRent=10000`, `maxRent=12000` (requires adding `minRent`).
- Move‑in date filtering:
  - Parse Swedish/English dates, compare to `moveIn`/`available_from` across sources.
- UI chips for active filters with one‑click clears (city/rooms/budget/areas).
- Pagination: "show me more" to fetch next batch of results.

**Medium-term:**
- Scraper integration guide & adapters (function or HTTP interfaces) with retries/rate limits.
- Optional on‑demand scrape fallback when cache is empty for a city.
- Better dedup across sources (same address/size).
- Result explanations per listing ("under budget by 500 kr", "in Uppsala, Rosendal").
- Unit tests for parsing, merging, filtering, normalization, and intent classification.
- Streaming responses: SSE or WebSocket for real-time typing effect from backend.

**Longer-term:**
- Multi-language support (detect user language, respond accordingly).
- Voice input/output integration.
- Saved searches & email notifications for new matches.
- Docker/Compose for reproducible deployment.
- Background job runner (e.g., APScheduler/Celery) for scheduled scrapes and translations.
- LLM re‑ranking of top candidates using richer text (still respecting privacy and cost).
- Analytics dashboard (popular cities, avg search budget, conversion rates).

## Troubleshooting

- **Seeing the same results after a scrape?** Ensure your job wrote to `bostad.json` / `heimstaden.json`. The server auto‑reloads on the next request; you can also `POST /api/reload`.
- **Chat replies generic?** The LLM will fall back to heuristics if unavailable; try being explicit (city, rooms, budget). Also verify `GEMINI_API_KEY` is set in `.env`.
- **gRPC/absl warnings (harmless)?** Silence by exporting `GLOG_minloglevel=2` and `GRPC_VERBOSITY=ERROR` before running the server.
- **Model not found error?** Ensure you have access to `gemini-2.0-flash-exp`. Check Google AI Studio for model availability in your region.
