import argparse
import csv
import json
import os
import string
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

print(">>> AI GENERATOR RUNNING <<<")

load_dotenv()

ap = argparse.ArgumentParser()
ap.add_argument("--force", action="store_true", help="Overwrite existing drafts")
args = ap.parse_args()

INPUT_FILE = "input/pages.csv"
PROMPT_FILE = Path("input/prompt_template.txt")
OUTPUT_DIR = Path("drafts")
OUTPUT_DIR.mkdir(exist_ok=True)

# Requires OPENAI_API_KEY in .env (project root)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def load_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        raise SystemExit(f"Missing prompt template file: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


def template_fields(t: str) -> set[str]:
    """
    Extract {placeholders} used by str.format in the template.
    This helps detect accidental placeholders like {city} or unescaped JSON braces.
    """
    fields: set[str] = set()
    for _, field, _, _ in string.Formatter().parse(t):
        if field:
            # strip format spec / conversion if present
            field = field.split("!")[0].split(":")[0]
            fields.add(field)
    return fields


def safe_format_template(template: str, values: Dict[str, str]) -> str:
    """
    Fail fast with a helpful error if the template contains unknown placeholders,
    rather than crashing with a KeyError mid-run.
    """
    needed = template_fields(template)
    missing = needed - set(values.keys())
    if missing:
        raise ValueError(
            f"prompt_template.txt contains unknown placeholders: {sorted(missing)}. "
            f"Either remove them from the template or supply them in code."
        )
    return template.format(**values)


def generate_bundle(
    template: str,
    *,
    title: str,
    area: str,
    intent: str,
    meta_description_seed: str,
    primary_keyword_seed: str,
) -> Dict[str, Any]:
    """
    The CSV values are seeds (single input set). The model returns final values.

    Supported placeholders in prompt_template.txt:
      {title}, {area}, {intent},
      {seed_meta_description}, {seed_primary_key_word},
      {meta_description}, {primary_key_word}
    """
    values = {
        "title": title,
        "area": area,
        "intent": intent,
        "seed_meta_description": meta_description_seed or "",
        "seed_primary_key_word": primary_keyword_seed or "",
        "meta_description": meta_description_seed or "",
        "primary_key_word": primary_keyword_seed or "",
    }
    prompt = safe_format_template(template, values)

    # JSON mode: forces the model to output valid JSON
    resp = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
        text={"format": {"type": "json_object"}},
    )

    try:
        payload = json.loads(resp.output_text)
    except json.JSONDecodeError as e:
        # Useful for debugging without re-running multiple times
        raise ValueError(
            f"Model returned invalid JSON despite json_object mode. Error: {e}\n"
            f"Raw output:\n{resp.output_text}"
        ) from e

    required = [
        "meta_description",
        "primary_key_word",
        "cta_primary_headline",
        "cta_primary_text",
        "cta_secondary_headline",
        "cta_secondary_text",
        "html",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"Missing keys in model JSON: {missing}")

    # If seeds provided and model returns blanks, fall back to seeds.
    if meta_description_seed and not str(payload.get("meta_description", "")).strip():
        payload["meta_description"] = meta_description_seed
    if primary_keyword_seed and not str(payload.get("primary_key_word", "")).strip():
        payload["primary_key_word"] = primary_keyword_seed

    return payload


def main() -> None:
    template = load_prompt_template()

    # Hungarian-safe CSV import (Excel/Windows often uses cp1250)
    with open(INPUT_FILE, newline="", encoding="cp1250") as f:
        reader = csv.DictReader(f)

        for row in reader:
            slug = (row.get("slug") or "").strip()
            title = (row.get("title") or "").strip()
            area = (row.get("area") or "").strip()
            intent = (row.get("intent") or "").strip()

            if not slug or not title:
                continue

            # 1) ALWAYS skip pillar rows (gen=stub)
            gen = (row.get("gen") or "").strip().lower()
            if gen == "stub":
                print(f"Skip AI (pillar/gen=stub): {slug}")
                continue

            # 2) Skip if already generated (unless --force)
            out_file = OUTPUT_DIR / f"{slug}.json"
            if out_file.exists() and not args.force:
                print(f"Skip (draft exists): {out_file}")
                continue

            # Seeds (single input set)
            meta_description_seed = (row.get("meta_description") or "").strip()
            primary_keyword_seed = (row.get("primary_key_word") or "").strip()

            bundle = generate_bundle(
                template,
                title=title,
                area=area,
                intent=intent,
                meta_description_seed=meta_description_seed,
                primary_keyword_seed=primary_keyword_seed,
            )

            draft = {
                "slug": slug,
                "title": title,
                "area": area,
                "intent": intent,
                "meta_description": str(bundle["meta_description"]).strip(),
                "primary_key_word": str(bundle["primary_key_word"]).strip(),
                "cta_primary_headline": str(bundle["cta_primary_headline"]).strip(),
                "cta_primary_text": str(bundle["cta_primary_text"]).strip(),
                "cta_secondary_headline": str(bundle["cta_secondary_headline"]).strip(),
                "cta_secondary_text": str(bundle["cta_secondary_text"]).strip(),
                "html": str(bundle["html"]).strip(),
            }

            with open(out_file, "w", encoding="utf-8") as out:
                json.dump(draft, out, indent=2, ensure_ascii=False)

            print(f"Generated AI draft: {out_file}")


if __name__ == "__main__":
    main()
