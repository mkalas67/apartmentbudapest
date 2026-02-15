import argparse
import csv
import io
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

from dotenv import load_dotenv

from site_config import load_site_config, site_input_path

load_dotenv()

CTA1_START = "<!-- AB:CTA1:START -->"
CTA1_END = "<!-- AB:CTA1:END -->"
CTA2_START = "<!-- AB:CTA2:START -->"
CTA2_END = "<!-- AB:CTA2:END -->"

RELATED_START = "<!-- AB:RELATED:START -->"
RELATED_END = "<!-- AB:RELATED:END -->"

# Partner resolution (no affiliates.json). Extend as needed.
# If pages.csv contains direct URLs (e.g. /go/booking) those will be used as-is.
PARTNERS = {
    "booking": {"url": "/go/booking", "label": "Check availability"},
    "spotahome": {"url": "/go/spotahome", "label": "Browse monthly rentals"},
    "housinganywhere": {"url": "/go/housinganywhere", "label": "View rentals"},
    "airbnb": {"url": "/go/airbnb", "label": "See listings"},
}

ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1250", "iso-8859-2", "cp1252")


def read_text_best_effort(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ENCODINGS_TO_TRY:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Could not decode {path}. Tried: {', '.join(ENCODINGS_TO_TRY)}")


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def remove_marked_block(html: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.S)
    return re.sub(pattern, "", html).strip()


def parse_district_number(slug: str) -> Optional[int]:
    m = re.search(r"district-(\d+)-apartments", slug)
    return int(m.group(1)) if m else None


def looks_like_url(s: str) -> bool:
    s = s.strip().lower()
    return s.startswith("/") or s.startswith("http://") or s.startswith("https://")


def resolve_partner(value: str, fallback_label: str) -> Optional[Dict[str, str]]:
    """
    Accepts either:
      - a partner key in PARTNERS (e.g. "booking")
      - a direct URL/path (e.g. "/go/booking" or "https://...")
    """
    value = (value or "").strip()
    if not value:
        return None

    key = value.lower()
    if key in PARTNERS:
        return PARTNERS[key]

    if looks_like_url(value):
        return {"url": value, "label": fallback_label}

    return None


def load_pages_index(pages_csv: Path) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    """
    Returns:
      - pages index keyed by slug
      - pillar slugs (derived from gen=stub rows)
    """
    if not pages_csv.exists():
        raise SystemExit(f"Missing {pages_csv}")

    text = read_text_best_effort(pages_csv)
    reader = csv.DictReader(io.StringIO(text))

    idx: Dict[str, Dict[str, str]] = {}
    pillar_slugs: List[str] = []

    for row in reader:
        slug = (row.get("slug") or "").strip()
        if not slug:
            continue

        gen = (row.get("gen") or "").strip().lower()
        if gen == "stub":
            pillar_slugs.append(slug)

        idx[slug] = {
            "title": (row.get("title") or slug).strip(),
            "intent": (row.get("intent") or "").strip().lower(),
            "area": (row.get("area") or "").strip(),
            "gen": gen,
            "primary_partner": (row.get("primary_partner") or "").strip(),
            "secondary_partner": (row.get("secondary_partner") or "").strip(),
        }

    return idx, pillar_slugs


def available_slugs_for_lang(drafts_root: Path, site_key: str, lang: str) -> Set[str]:
    """
    Return the set of slugs that have draft JSON files in drafts/<site>/<lang>/.
    """
    p = drafts_root / site_key / lang
    if not p.exists():
        return set()
    return {fp.stem for fp in p.glob("*.json") if fp.name != "_manifest.json" and not fp.name.startswith("_manifest")}


def make_href(target_slug: str, *, lang: str, translated_slugs: Set[str]) -> str:
    """
    Language-aware internal link strategy for WP page hierarchy:
      - If lang == 'en': /<slug>/
      - Else: prefer /<lang>/<slug>/ if that translated page exists, else fallback to /<slug>/
    """
    target_slug = target_slug.strip().strip("/")
    if lang == "en":
        return f"/{target_slug}/"
    if target_slug in translated_slugs:
        return f"/{lang}/{target_slug}/"
    return f"/{target_slug}/"


def build_related_links(
    current_slug: str,
    pages: Dict[str, Dict[str, str]],
    pillar_slugs: List[str],
    *,
    lang: str,
    translated_slugs: Set[str],
) -> str:
    """
    Related links block:
    - Pillars: gen=stub rows from THIS site's pages.csv
    - Neighbor districts: n-1 and n+1 (if present in THIS site's pages.csv)
    - Links prefer same-language URLs when translated draft exists
    """
    links: List[Tuple[str, str]] = []

    def add_link(target_slug: str):
        if target_slug not in pages:
            return
        title = pages[target_slug].get("title") or target_slug
        href = make_href(target_slug, lang=lang, translated_slugs=translated_slugs)
        links.append((href, title))

    # Pillars (site-scoped)
    for p in pillar_slugs:
        add_link(p)

    # Neighbor districts (site-scoped)
    n = parse_district_number(current_slug)
    if n is not None:
        for nn in (n - 1, n + 1):
            neighbor = f"district-{nn}-apartments"
            if neighbor in pages:
                add_link(neighbor)

    # De-dupe preserving order
    seen = set()
    deduped: List[Tuple[str, str]] = []
    for href, text in links:
        if href in seen:
            continue
        seen.add(href)
        deduped.append((href, text))

    items_html = "\n".join(
        f'    <li><a href="{html_escape(href)}">{html_escape(text)}</a></li>'
        for href, text in deduped
    )

    return (
        f"{RELATED_START}\n"
        f'<div class="ab-related" data-ab-block="related">\n'
        f"  <h2>Related guides</h2>\n"
        f"  <ul>\n"
        f"{items_html}\n"
        f"  </ul>\n"
        f"</div>\n"
        f"{RELATED_END}"
    )


def build_cta_block(which: str, headline: str, text: str, url: str, label: str) -> str:
    start = CTA1_START if which == "cta1" else CTA2_START
    end = CTA1_END if which == "cta1" else CTA2_END

    return (
        f"{start}\n"
        f'<div class="ab-cta" data-ab-block="{which}">\n'
        f'  <div class="ab-cta-inner">\n'
        f"    <p><strong>{html_escape(headline)}</strong></p>\n"
        f"    <p>{html_escape(text)}</p>\n"
        f'    <p><a class="ab-cta-btn" href="{html_escape(url)}">{html_escape(label)}</a></p>\n'
        f"  </div>\n"
        f"</div>\n"
        f"{end}"
    )


def inject_into_html(
    html: str,
    draft: Dict[str, Any],
    page_row: Dict[str, str],
    pages: Dict[str, Dict[str, str]],
    pillar_slugs: List[str],
    *,
    lang: str,
    translated_slugs: Set[str],
) -> str:
    # Idempotent cleanup
    html = remove_marked_block(html, CTA1_START, CTA1_END)
    html = remove_marked_block(html, CTA2_START, CTA2_END)
    html = remove_marked_block(html, RELATED_START, RELATED_END)

    slug = (draft.get("slug") or "").strip()

    # CTA copy from draft JSON
    cta1_h = (draft.get("cta_primary_headline") or "").strip()
    cta1_t = (draft.get("cta_primary_text") or "").strip()
    cta2_h = (draft.get("cta_secondary_headline") or "").strip()
    cta2_t = (draft.get("cta_secondary_text") or "").strip()

    # Partner href/label from pages.csv
    primary_partner_val = (page_row.get("primary_partner") or "").strip()
    secondary_partner_val = (page_row.get("secondary_partner") or "").strip()

    primary = resolve_partner(primary_partner_val, fallback_label="View options")
    secondary = resolve_partner(secondary_partner_val, fallback_label="View options")

    cta1 = ""
    if cta1_h and cta1_t and primary:
        cta1 = build_cta_block("cta1", cta1_h, cta1_t, primary["url"], primary["label"])
    else:
        print(f"[WARN] CTA1 not injected for {slug} (missing copy or primary_partner)")

    cta2 = ""
    if cta2_h and cta2_t and secondary:
        cta2 = build_cta_block("cta2", cta2_h, cta2_t, secondary["url"], secondary["label"])
    else:
        print(f"[WARN] CTA2 not injected for {slug} (missing copy or secondary_partner)")

    related = build_related_links(slug, pages, pillar_slugs, lang=lang, translated_slugs=translated_slugs)

    # Insert CTA1 right after first </h2>
    if cta1:
        if "</h2>" in html:
            before, after = html.split("</h2>", 1)
            html = before + "</h2>\n" + cta1 + "\n" + after
        else:
            html = cta1 + "\n" + html

    # Insert CTA2 + Related right before FAQ
    faq_marker = "<h2>FAQ</h2>"
    insert_tail = "\n".join([blk for blk in [cta2, related] if blk.strip()])

    if faq_marker in html and insert_tail:
        html = html.replace(faq_marker, insert_tail + "\n" + faq_marker, 1)
    elif insert_tail:
        html = html + "\n\n" + insert_tail

    return html.strip()


def iter_drafts(drafts_dir: Path) -> List[Path]:
    if any(drafts_dir.glob("*.json")):
        return sorted(drafts_dir.glob("*.json"))
    return sorted(drafts_dir.glob("**/*.json"))


def infer_lang_from_path(path: Path, site_key: str) -> str:
    """
    drafts/<site>/<lang>/<slug>.json -> returns <lang>
    If not inferable, default to 'en'.
    """
    parts = path.parts
    try:
        idx = parts.index("drafts")
        if idx + 2 < len(parts) and parts[idx + 1] == site_key:
            return parts[idx + 2].lower()
    except ValueError:
        pass
    return "en"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.getenv("SITE_KEY", "default"))
    ap.add_argument("--lang", default=None, help="If omitted, process all languages under drafts/<site>/")
    ap.add_argument("--dir", default="drafts", help="Drafts root directory")
    args = ap.parse_args()

    site = load_site_config(args.site)
    pages_csv = site_input_path(site.site_key, "pages.csv")
    pages, pillar_slugs = load_pages_index(pages_csv)

    drafts_root = Path(args.dir)
    if not drafts_root.exists():
        raise SystemExit("drafts/ not found. Run generate.py first.")

    if args.lang:
        drafts_dir = drafts_root / site.site_key / args.lang.strip().lower()
    else:
        drafts_dir = drafts_root / site.site_key

    if not drafts_dir.exists():
        raise SystemExit(f"Drafts directory not found: {drafts_dir}")

    print(f"Using pages: {pages_csv}")
    print(f"Processing drafts: {drafts_dir}")

    # Precompute translated slugs for explicit lang runs; for multi-lang run we compute per draft lang.
    translated_slugs_for_explicit_lang: Set[str] = set()
    explicit_lang = None
    if args.lang:
        explicit_lang = args.lang.strip().lower()
        translated_slugs_for_explicit_lang = available_slugs_for_lang(drafts_root, site.site_key, explicit_lang)

    for draft_path in iter_drafts(drafts_dir):
        if draft_path.name.startswith("_manifest"):
            continue

        with draft_path.open(encoding="utf-8") as f:
            draft = json.load(f)

        # Safety check: if draft says it's from another site, skip it.
        draft_site = (draft.get("site_key") or "").strip()
        if draft_site and draft_site != site.site_key:
            print(f"[WARN] Skip draft from different site ({draft_site}): {draft_path}")
            continue

        slug = (draft.get("slug") or draft_path.stem).strip()
        draft["slug"] = slug

        # Determine language context for link building
        draft_lang = (draft.get("lang") or "").strip().lower()
        if not draft_lang:
            draft_lang = explicit_lang or infer_lang_from_path(draft_path, site.site_key)

        if explicit_lang:
            translated_slugs = translated_slugs_for_explicit_lang
        else:
            translated_slugs = available_slugs_for_lang(drafts_root, site.site_key, draft_lang)

        page_row = pages.get(slug, {})
        html = draft.get("html") or ""
        draft["html"] = inject_into_html(
            html,
            draft,
            page_row,
            pages,
            pillar_slugs,
            lang=draft_lang,
            translated_slugs=translated_slugs,
        )

        with draft_path.open("w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2, ensure_ascii=False)

        print(f"Injected blocks into: {draft_path}")


if __name__ == "__main__":
    main()
