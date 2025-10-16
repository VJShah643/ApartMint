# ApartMint
ApartMint is a smart apartment-hunting chatbot that helps users find homes through natural conversation. It scrapes listings from multiple websites, understands preferences like location, budget, and rooms, and recommends the best matches in real time — making apartment searching smooth and refreshingly minty 🍃.

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

