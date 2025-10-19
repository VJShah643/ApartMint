import json
import argparse
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

def translate_apartment_data(data: dict, source_lang: str = "sv", target_lang: str = "en", verbose: bool = True) -> dict:
    """Translate all text fields in an apartment from source_lang to target_lang.

    Args:
        data: Apartment dict.
        source_lang: Source language code (default 'sv').
        target_lang: Target language code (default 'en').
        verbose: If True, print field-by-field translations.
    """
    translator = GoogleTranslator(source=source_lang, target=target_lang)
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
            if verbose:
                print(f"Translated '{key}': {value} -> {translated[key]}")
        except Exception:
            translated[key] = value
    return translated

def main():
    parser = argparse.ArgumentParser(description="Clean and translate apartment listings JSON.")
    parser.add_argument("--input", "-i", default="heimstaden.json", help="Path to input JSON file (default: heimstaden.json)")
    parser.add_argument("--source", "-s", default="sv", help="Source language code (default: sv)")
    parser.add_argument("--target", "-t", default="en", help="Target language code (default: en)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Reduce logging output")
    parser.add_argument("--output-prefix", default=None, help="Custom output filename prefix (default: <input_basename>_translated)")

    args = parser.parse_args()

    # Load JSON
    with open(args.input, "r", encoding="utf-8") as f:
        apartments = json.load(f)

    # Remove None entries and empty apartments
    non_empty_apartments = [apt for apt in apartments if apt and not is_empty_apartment(apt)]
    if not args.quiet:
        print(
            f"Kept {len(non_empty_apartments)} non-empty entries out of {len(apartments)} total"
        )

    # Translate them
    translated_apartments = [
        translate_apartment_data(apt, source_lang=args.source, target_lang=args.target, verbose=not args.quiet)
        for apt in non_empty_apartments
    ]

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_prefix = args.output_prefix
    if not base_prefix:
        # derive from input file name
        import os

        base = os.path.basename(args.input)
        name, _ = os.path.splitext(base)
        base_prefix = f"{name}_translated"

    output_filename = f"{base_prefix}_{timestamp}.json"

    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(translated_apartments, f, ensure_ascii=False, indent=4)

    print(f"Translated data saved to {output_filename}")


if __name__ == "__main__":
    main()
