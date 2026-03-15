import argparse
import csv
import json
import os
import string
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from site_config import load_site_config, site_input_path

print(">>> AI GENERATOR RUNNING <<<")

load_dotenv()

ap = argparse.ArgumentParser()
ap.add_argument("--site", default=os.getenv("SITE_KEY", "default"))
ap.add_argument("--lang", default=None)
ap.add_argument("--force", action="store_true", help="Overwrite existing drafts")
args = ap.parse_args()

site = load_site_config(args.site)
lang = (args.lang or site.default_language or "en").strip().lower()
city = site.site_key.replace("-", " ").title()

INPUT_FILE = site_input_path(site.site_key, "pages.csv")
PROMPT_FILE = site_input_path(site.site_key, "prompt_template.txt")
OUTPUT_DIR = Path("drafts") / site.site_key / lang
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def load_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        raise SystemExit(f"Missing prompt template file: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


def template_fields(t: str) -> set[str]:
    fields: set[str] = set()
    for _, field, _, _ in string.Formatter().parse(t):
        if field:
            field = field.split("!")[0].split(":")[0]
            fields.add(field)
    return fields


def safe_format_template(template: str, values: Dict[str, str]) -> str:
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
    city: str,
    title: str,
    area: str,
    intent: str,
    meta_description_input: str,
    primary_keyword_input: str,
) -> Dict[str, Any]:
    """
    CSV values are treated as authoritative inputs where present.
    AI should mainly generate html + CTA copy, and only fill SEO fields if blank.

    Supported placeholders in prompt_template.txt:
      {city}
      {title}
      {area}
      {intent}
      {meta_description}
      {primary_key_word}
      {has_meta_description}
      {has_primary_key_word}
    """
    values = {
        "city": city,
        "title": title,
        "area": area,
        "intent": intent,
        "meta_description": meta_description_input or "",
        "primary_key_word": primary_keyword_input or "",
        "has_meta_description": "yes" if meta_description_input.strip() else "no",
        "has_primary_key_word": "yes" if primary_keyword_input.strip() else "no",
    }

    prompt = safe_format_template(template, values)

    resp = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
        text={"format": {"type": "json_object"}},
    )

    try:
        payload = json.loads(resp.output_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model returned invalid JSON despite json_object mode. Error: {e}\n"
            f"Raw output:\n{resp.output_text}"
        ) from e

    required = [
        "cta_primary_headline",
        "cta_primary_text",
        "cta_secondary_headline",
        "cta_secondary_text",
        "html",
    ]
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"Missing keys in model JSON: {missing}")

    # Preserve CSV values when present.
    final_meta_description = meta_description_input.strip()
    if not final_meta_description:
        final_meta_description = str(payload.get("meta_description", "")).strip()

    final_primary_keyword = primary_keyword_input.strip()
    if not final_primary_keyword:
        final_primary_keyword = str(payload.get("primary_key_word", "")).strip()

    payload["meta_description"] = final_meta_description
    payload["primary_key_word"] = final_primary_keyword

    return payload


def main() -> None:
    template = load_prompt_template()

    with open(INPUT_FILE, newline="", encoding="cp1250") as f:
        reader = csv.DictReader(f)

        for row in reader:
            slug = (row.get("slug") or "").strip()
            title = (row.get("title") or "").strip()
            area = (row.get("area") or "").strip()
            intent = (row.get("intent") or "").strip()

            if not slug or not title:
                continue

            gen = (row.get("gen") or "").strip().lower()
            if gen == "stub":
                print(f"Skip AI (pillar/gen=stub): {slug}")
                continue

            out_file = OUTPUT_DIR / f"{slug}.json"
            if out_file.exists() and not args.force:
                print(f"Skip (draft exists): {out_file}")
                continue

            meta_description_input = (row.get("meta_description") or "").strip()
            primary_keyword_input = (
                row.get("primary_key_word")
                or row.get("primary_keyword")
                or ""
            ).strip()

            bundle = generate_bundle(
                template,
                city=city,
                title=title,
                area=area,
                intent=intent,
                meta_description_input=meta_description_input,
                primary_keyword_input=primary_keyword_input,
            )

            draft = {
                "slug": slug,
                "title": title,
                "area": area,
                "intent": intent,
                "meta_description": str(bundle.get("meta_description", "")).strip(),
                "primary_key_word": str(bundle.get("primary_key_word", "")).strip(),
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