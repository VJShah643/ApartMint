import json
from datetime import datetime
from deep_translator import GoogleTranslator

def is_empty_apartment(data: dict) -> bool:
    """Return True if apartment data has no meaningful fields."""
    if not isinstance(data, dict):  # skip None or wrong types
        return True
    ignore_keys = {"url"}
    for key, value in data.items():
        if key not in ignore_keys and value not in (None, "", [], {}):
            return False
    return True

def translate_apartment_data(data: dict) -> dict:
    """Translate all Swedish text fields in an apartment to English."""
    translator = GoogleTranslator(source="sv", target="en")
    translated = {}
    for key, value in data.items():
        try:
            if isinstance(value, str) and value.strip():
                translated[key] = translator.translate(value)
            elif isinstance(value, list):
                translated[key] = [
                    translator.translate(v) if isinstance(v, str) and v.strip() else v
                    for v in value
                ]
            else:
                translated[key] = value
            print(f"Translated '{key}': {value} -> {translated[key]}")
        except Exception:
            translated[key] = value
    return translated

# Load JSON
with open("heimstadin.json", "r", encoding="utf-8") as f:
    apartments = json.load(f)

# Remove None entries and empty apartments
non_empty_apartments = [
    apt for apt in apartments if apt and not is_empty_apartment(apt)
]
print(f"Kept {len(non_empty_apartments)} non-empty entries out of {len(apartments)} total")

# Translate them
translated_apartments = [translate_apartment_data(apt) for apt in non_empty_apartments]

# Save
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_filename = f"heimstaden_translated_{timestamp}.json"

with open(output_filename, "w", encoding="utf-8") as f:
    json.dump(translated_apartments, f, ensure_ascii=False, indent=4)

print(f"Translated data saved to {output_filename}")
