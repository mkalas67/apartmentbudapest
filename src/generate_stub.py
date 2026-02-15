import csv
import json
from pathlib import Path
import argparse

print(">>> STUB GENERATOR RUNNING <<<")

INPUT_FILE = "input/pages.csv"
OUTPUT_DIR = Path("drafts")
OUTPUT_DIR.mkdir(exist_ok=True)

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Overwrite existing drafts/<slug>.json")
    ap.add_argument("--slugs", default="", help="Comma-separated slugs to generate (optional)")
    args = ap.parse_args()

    only_slugs = {s.strip() for s in args.slugs.split(",") if s.strip()}

    with open(INPUT_FILE, newline="", encoding="cp1250") as f:
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

            out_file = OUTPUT_DIR / f"{slug}.json"
            if out_file.exists() and not args.force:
                print(f"Skip (exists): {out_file}")
                continue

            html = SKELETON.format(title=title, area=area, intent=intent)

            draft = {"slug": slug, "title": title, "html": html}
            with open(out_file, "w", encoding="utf-8") as out:
                json.dump(draft, out, indent=2, ensure_ascii=False)

            print(f"Generated STUB draft: {out_file}")

if __name__ == "__main__":
    main()
