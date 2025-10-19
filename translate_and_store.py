from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _translator():
    try:
        from deep_translator import GoogleTranslator  # type: ignore
        return GoogleTranslator(source="sv", target="en")
    except Exception:
        return None


def selective_translate(item: Dict[str, Any], fields: Iterable[str] = ("description", "facilities", "location", "address", "area")) -> Dict[str, Any]:
    """Translate selected string or list-of-string fields into English, storing alongside originals.

    Adds keys with suffix _en for translated values, e.g., description_en, facilities_en.
    If translator unavailable, returns item unchanged.
    """
    tr = _translator()
    if tr is None:
        return item
    out = dict(item)
    for key in fields:
        if key not in item or item[key] in (None, ""):
            continue
        val = item[key]
        try:
            if isinstance(val, str):
                out[f"{key}_en"] = tr.translate(val)
            elif isinstance(val, list):
                out[f"{key}_en"] = [tr.translate(x) if isinstance(x, str) and x.strip() else x for x in val]
        except Exception:
            # Best effort; skip failures per field
            pass
    out.setdefault("translated_at", datetime.utcnow().isoformat(timespec="seconds") + "Z")
    return out


def upsert_listings(file_path: Path, new_items: List[Dict[str, Any]], key: str = "url") -> int:
    """Upsert items into a JSON array file by unique key; returns count of inserted/updated items."""
    existing: List[Dict[str, Any]] = []
    if file_path.exists():
        try:
            existing = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    index = {it.get(key): i for i, it in enumerate(existing) if it and it.get(key)}
    changed = 0
    for it in new_items:
        it = dict(it)
        it.setdefault("scraped_at", datetime.utcnow().isoformat(timespec="seconds") + "Z")
        uid = it.get(key)
        if not uid:
            continue
        if uid in index:
            existing[index[uid]] = it
        else:
            index[uid] = len(existing)
            existing.append(it)
        changed += 1
    file_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed
