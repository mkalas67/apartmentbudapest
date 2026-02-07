import json
from pathlib import Path

AFFILIATES_FILE = "input/affiliates.json"

CTA_BLOCK_TEMPLATE = """
<div class="ab-cta">
  <div class="ab-cta-inner">
    <p><strong>{headline}</strong></p>
    <p>{text}</p>
    <p>
      <a class="ab-cta-btn" href="{url}">{label}</a>
    </p>
  </div>
</div>
"""

def load_affiliates():
    with open(AFFILIATES_FILE, encoding="utf-8") as f:
        return json.load(f)

def inject_ctas(html: str, primary: dict, secondary: dict) -> str:
    # CTA 1: after first </h2> section (intended after "Overview")
    cta1 = CTA_BLOCK_TEMPLATE.format(
        headline="Shortlist options in minutes",
        text="Use a reputable platform to compare availability and filters quickly.",
        url=primary["url"],
        label=primary["label"],
    )

    # CTA 2: near the end, before FAQ heading if present
    cta2 = CTA_BLOCK_TEMPLATE.format(
        headline="Ready to start contacting places?",
        text="If you’re planning a move, start with verified listings and clear cancellation terms.",
        url=secondary["url"],
        label=secondary["label"],
    )

    # Inject CTA1 after first </h2> block (best-effort)
    if "</h2>" in html:
        parts = html.split("</h2>", 1)
        html = parts[0] + "</h2>\n" + cta1 + "\n" + parts[1]
    else:
        html = cta1 + "\n" + html

    # Inject CTA2 before FAQ if present
    faq_marker = "<h2>FAQ</h2>"
    if faq_marker in html:
        html = html.replace(faq_marker, cta2 + "\n" + faq_marker, 1)
    else:
        html = html + "\n" + cta2

    return html

def main():
    affiliates = load_affiliates()
    primary = affiliates["primary"]
    secondary = affiliates["secondary"]

    drafts_dir = Path("drafts")
    for path in drafts_dir.glob("*.json"):
        with open(path, encoding="utf-8") as f:
            draft = json.load(f)

        draft["html"] = inject_ctas(draft["html"], primary, secondary)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2, ensure_ascii=False)

        print(f"Injected CTAs into: {path}")

if __name__ == "__main__":
    main()
