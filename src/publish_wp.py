import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

WP_BASE_URL = os.environ["WP_BASE_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
PAGES_API = f"{WP_BASE_URL}/wp-json/wp/v2/pages"


def get_page_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    r = requests.get(
        PAGES_API,
        params={
            "slug": slug,
            "status": "any",   # include drafts
            "per_page": 100,
            "context": "edit",
        },
        auth=auth,
        timeout=30,
    )
    r.raise_for_status()
    items = r.json()
    if len(items) > 1:
        raise RuntimeError(f"Multiple pages found for slug '{slug}'. Clean duplicates in WP first.")
    return items[0] if items else None


def _post_with_fallback(url: str, payload: Dict[str, Any]) -> requests.Response:
    """
    Try full payload. If WP rejects unsupported fields (excerpt/meta), retry without them.
    """
    r = requests.post(url, json=payload, auth=auth, timeout=30)
    if r.status_code < 400:
        return r

    try:
        err = r.json()
        bad_params = (err.get("data") or {}).get("params") or {}
    except Exception:
        bad_params = {}

    # Typical WP error: data.params includes invalid fields
    retry_payload = dict(payload)

    if "excerpt" in bad_params and "excerpt" in retry_payload:
        retry_payload.pop("excerpt", None)

    if "meta" in bad_params and "meta" in retry_payload:
        retry_payload.pop("meta", None)

    # If we removed anything, retry once
    if retry_payload != payload:
        r2 = requests.post(url, json=retry_payload, auth=auth, timeout=30)
        return r2

    return r  # original failure


def upsert_page(
    *,
    slug: str,
    title: str,
    html: str,
    status: str,
    meta_description: str = "",
    primary_key_word: str = "",
) -> Tuple[Dict[str, Any], str]:
    existing = get_page_by_slug(slug)

    payload: Dict[str, Any] = {
        "slug": slug,
        "title": title,
        "content": html,
        "status": status,
    }

    # SEO: meta description -> excerpt (WP core field)
    if meta_description.strip():
        payload["excerpt"] = meta_description.strip()

    # SEO: primary keyword -> custom meta (optional; WP must allow meta via REST)
    if primary_key_word.strip():
        payload["meta"] = {"ab_primary_key_word": primary_key_word.strip()}

    # Nice safety warning if you forgot to run inject.py
    if "AB:CTA" not in html and "AB:RELATED" not in html:
        print(f"[WARN] {slug}: No injected CTA/RELATED markers found in HTML. Did you run inject.py?")

    if existing:
        page_id = existing["id"]
        r = _post_with_fallback(f"{PAGES_API}/{page_id}", payload)
        if r.status_code >= 400:
            raise RuntimeError(f"Update failed for {slug}: {r.status_code} {r.text}")
        return r.json(), "updated"

    r = _post_with_fallback(PAGES_API, payload)
    if r.status_code >= 400:
        raise RuntimeError(f"Create failed for {slug}: {r.status_code} {r.text}")
    return r.json(), "created"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", default="draft", choices=["draft", "publish"], help="WP page status")
    ap.add_argument("--dir", default="drafts", help="Directory containing draft JSON files")
    args = ap.parse_args()

    drafts_dir = Path(args.dir)
    if not drafts_dir.exists():
        raise SystemExit(f"Drafts directory not found: {drafts_dir}")

    for path in sorted(drafts_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            draft = json.load(f)

        slug = (draft.get("slug") or path.stem).strip()
        title = (draft.get("title") or slug).strip()
        html = (draft.get("html") or "").strip()

        page, action = upsert_page(
            slug=slug,
            title=title,
            html=html,
            status=args.status,
            meta_description=(draft.get("meta_description") or ""),
            primary_key_word=(draft.get("primary_key_word") or ""),
        )

        print(action, slug, page.get("link"))


if __name__ == "__main__":
    main()
