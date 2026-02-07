import csv
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

print(">>> AI GENERATOR RUNNING <<<")

load_dotenv()

INPUT_FILE = "input/pages.csv"
OUTPUT_DIR = Path("drafts")
OUTPUT_DIR.mkdir(exist_ok=True)

# Requires OPENAI_API_KEY in .env (project root)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

PROMPT_TEMPLATE = """\
Write a helpful SEO page in HTML (NOT Markdown). Do NOT include <h1>.
No affiliate links, no platform names, no fake prices.
Length 800-1200 words.

Topic:
- City: Budapest
- Area: {area}
- Intent: {intent}

Use these exact <h2> headings:
1) Overview
2) Who this area is best for
3) What to expect (pros/cons)
4) Transport and walkability
5) Things to watch out for
6) Next steps

End with <h2>FAQ</h2> and 4 Q&As, using <h3> for questions.
"""

def generate_html(area: str, intent: str) -> str:
    prompt = PROMPT_TEMPLATE.format(area=area, intent=intent)
    resp = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
    )
    return resp.output_text.strip()

with open(INPUT_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        slug = row["slug"].strip()
        title = row["title"].strip()
        area = row["area"].strip()
        intent = row["intent"].strip()

        html = generate_html(area=area, intent=intent)

        draft = {
            "slug": slug,
            "title": title,
            "html": html,
        }

        out_file = OUTPUT_DIR / f"{slug}.json"
        with open(out_file, "w", encoding="utf-8") as out:
            json.dump(draft, out, indent=2, ensure_ascii=False)

        print(f"Generated AI draft: {out_file}")
