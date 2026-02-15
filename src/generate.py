import argparse
import csv
import json
import os
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from site_config import load_site_config, site_input_path

print(">>> AI GENERATOR RUNNING <<<")

# Load root .env first (OPENAI_API_KEY lives here)
load_dotenv()

ap = argparse.ArgumentParser()
ap.add_argument("--site", default=os.getenv("SITE_KEY", "default"))
ap.add_argument("--lang", default=None)
ap.add_argument("--force", action="store_true")
ap.add_argument("--env_dir", default="sites", help="Directory containing per-site env files (default: sites/)")
args = ap.parse_args()

# Load per-site env (CITY, WP creds, languages etc) and override anything already loaded
SITE_ENV_PATH = Path(args.env_dir) / f"{args.site}.env"
load_dotenv(dotenv_path=SITE_ENV_PATH, override=True)

site = load_site_config(args.site)
lang = (args.lang or site.default_language or "en").strip().lower()

INPUT_FILE = site_input_path(site.site_key, "pages.csv")
PROMPT_FILE = site_input_path(site.site_key, "prompt_template.txt")

OUTPUT_DIR = Path("drafts") / site.site_key / lang
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"

# Requires OPENAI_API_KEY in root .env
if "OPENAI_API_KEY" not in os.environ or not os.environ["OPENAI_API_KEY"].strip():
    raise SystemExit("Missing OPENAI_API_KEY in root .env")

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
    city: str,
) -> Dict[str, Any]:
    """
    The CSV values are seeds (single input set). The model returns final values.

    Supported placeholders in prompt_template.txt:
      {title}, {area}, {intent}, {city},
      {seed_meta_description}, {seed_primary_key_word},
      {meta_description}, {primary_key_word}
    """
    values = {
        "title": title,
        "area": area,
        "intent": intent,
        "city": city,
        "seed_meta_description": meta_description_seed or "",
        "seed_primary_key_word": primary_keyword_seed or "",
        "meta_description": meta_description_seed or "",
        "primary_key_word": primary_keyword_seed or "",
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

    if meta_description_seed and not str(payload.get("meta_description", "")).strip():
        payload["meta_description"] = meta_description_seed
    if primary_keyword_seed and not str(payload.get("primary_key_word", "")).strip():
        payload["primary_key_word"] = primary_keyword_seed

    return payload


def load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    return {
        "site_key": site.site_key,
        "lang": lang,
        "input_file": str(INPUT_FILE),
        "prompt_file": str(PROMPT_FILE),
        "site_env_file": str(SITE_ENV_PATH),
        "generated_at_utc": None,
        "pages": [],
    }


def write_manifest(manifest: Dict[str, Any]) -> None:
    manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    template = load_prompt_template()

    # Prefer CITY from per-site env; fall back to site config if present
    city = (os.getenv("CITY") or "").strip()
    if not city:
        city = (getattr(site, "city", "") or "").strip()

    if not city:
        raise SystemExit(f"Missing CITY in {SITE_ENV_PATH} (or site config). Add CITY=... to the site env.")

    print(f"Using site env: {SITE_ENV_PATH}")
    print(f"Using pages: {INPUT_FILE}")
    print(f"Using prompt: {PROMPT_FILE}")
    print(f"City: {city}")
    manifest = load_manifest()

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
                manifest["pages"].append({"slug": slug, "status": "skipped_stub"})
                continue

            # 2) Skip if already generated (unless --force)
            out_file = OUTPUT_DIR / f"{slug}.json"
            if out_file.exists() and not args.force:
                print(f"Skip (draft exists): {out_file}")
                manifest["pages"].append(
                    {"slug": slug, "status": "skipped_exists", "file": str(out_file)}
                )
                continue

            meta_description_seed = (row.get("meta_description") or "").strip()
            primary_keyword_seed = (row.get("primary_key_word") or "").strip()

            bundle = generate_bundle(
                template,
                title=title,
                area=area,
                intent=intent,
                meta_description_seed=meta_description_seed,
                primary_keyword_seed=primary_keyword_seed,
                city=city,
            )

            draft = {
                "site_key": site.site_key,
                "lang": lang,
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
            manifest["pages"].append({"slug": slug, "status": "generated", "file": str(out_file)})

    write_manifest(manifest)
    print(f"Manifest written: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
