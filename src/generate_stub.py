import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from site_config import load_site_config, site_input_path

print(">>> STUB GENERATOR RUNNING <<<")

load_dotenv()

SKELETON = """\
<h2>Overview</h2>
<p><em>TODO:</em> Write a short intro for <strong>{title}</strong>. Explain what the page covers and who it helps.</p>

<h2>Who this is best for</h2>
<ul>
  <li><em>TODO:</em> Persona / use case</li>
  <li><em>TODO:</em> Persona / use case</li>
</ul>

<h2>What to expect (pros/cons)</h2>
<ul>
  <li><strong>Pros:</strong> <em>TODO</em></li>
  <li><strong>Cons:</strong> <em>TODO</em></li>
</ul>

<h2>Transport and walkability</h2>
<p><em>TODO:</em> Key connections, commute patterns, what’s “easy” vs “annoying”.</p>

<h2>Things to watch out for</h2>
<ul>
  <li><em>TODO:</em> Scams / paperwork / deposits / hidden costs</li>
  <li><em>TODO:</em> Timing / availability / seasonality</li>
</ul>

<h2>Next steps</h2>
<ol>
  <li><em>TODO:</em> How to shortlist</li>
  <li><em>TODO:</em> What to prepare (docs/budget)</li>
  <li><em>TODO:</em> How to book/enquire</li>
</ol>

<h2>FAQ</h2>
<h3><em>TODO:</em> Question 1</h3>
<p><em>TODO:</em> Answer 1</p>
<h3><em>TODO:</em> Question 2</h3>
<p><em>TODO:</em> Answer 2</p>
<h3><em>TODO:</em> Question 3</h3>
<p><em>TODO:</em> Answer 3</p>
<h3><em>TODO:</em> Question 4</h3>
<p><em>TODO:</em> Answer 4</p>
"""


def load_manifest(manifest_path: Path, *, site_key: str, lang: str, input_file: Path) -> Dict[str, Any]:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "site_key": site_key,
        "lang": lang,
        "input_file": str(input_file),
        "generated_at_utc": None,
        "pages": [],
    }


def write_manifest(manifest_path: Path, manifest: Dict[str, Any]) -> None:
    manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.getenv("SITE_KEY", "default"))
    ap.add_argument("--lang", default=None)
    ap.add_argument("--force", action="store_true", help="Overwrite existing drafts")
    ap.add_argument("--slugs", default="", help="Comma-separated slugs to generate (optional)")
    args = ap.parse_args()

    site = load_site_config(args.site)
    lang = (args.lang or site.default_language or "en").strip().lower()

    input_file = site_input_path(site.site_key, "pages.csv")

    output_dir = Path("drafts") / site.site_key / lang
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "_manifest_stub.json"
    manifest = load_manifest(manifest_path, site_key=site.site_key, lang=lang, input_file=input_file)

    only_slugs = {s.strip() for s in args.slugs.split(",") if s.strip()}

    print(f"Using pages: {input_file}")
    print(f"Writing stubs to: {output_dir}")

    with open(input_file, newline="", encoding="cp1250") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("pages.csv missing header row")

        for row in reader:
            slug = (row.get("slug") or "").strip()
            title = (row.get("title") or "").strip()
            area = (row.get("area") or "").strip()
            intent = (row.get("intent") or "").strip()
            gen = (row.get("gen") or "").strip().lower()

            if not slug or not title:
                continue

            if only_slugs and slug not in only_slugs:
                continue

            # Only generate stubs for rows explicitly marked gen=stub
            if gen != "stub":
                continue

            out_file = output_dir / f"{slug}.json"
            if out_file.exists() and not args.force:
                print(f"Skip (exists): {out_file}")
                manifest["pages"].append({"slug": slug, "status": "skipped_exists", "file": str(out_file)})
                continue

            html = SKELETON.format(title=title, area=area, intent=intent)

            draft = {
                "site_key": site.site_key,
                "lang": lang,
                "slug": slug,
                "title": title,
                "area": area,
                "intent": intent,
                "meta_description": "",
                "primary_key_word": "",
                "cta_primary_headline": "",
                "cta_primary_text": "",
                "cta_secondary_headline": "",
                "cta_secondary_text": "",
                "html": html,
                "is_stub": True,
            }

            with open(out_file, "w", encoding="utf-8") as out:
                json.dump(draft, out, indent=2, ensure_ascii=False)

            print(f"Generated STUB draft: {out_file}")
            manifest["pages"].append({"slug": slug, "status": "generated", "file": str(out_file)})

    write_manifest(manifest_path, manifest)
    print(f"Stub manifest written: {manifest_path}")


if __name__ == "__main__":
    main()
