import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from site_config import load_site_config

load_dotenv()


def wp_pages_api(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/wp-json/wp/v2/pages"


def get_pages_by_slug(pages_api: str, auth: HTTPBasicAuth, slug: str) -> List[Dict[str, Any]]:
    r = requests.get(
        pages_api,
        params={
            "slug": slug,
            "per_page": 100,
            # "context": "edit",  # keep if your app password user has rights; otherwise comment out
        },
        auth=auth,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def find_page_by_slug_and_parent(
    pages_api: str, auth: HTTPBasicAuth, slug: str, parent_id: int
) -> Optional[Dict[str, Any]]:
    items = get_pages_by_slug(pages_api, auth, slug)
    matches = [p for p in items if int(p.get("parent", 0)) == int(parent_id)]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple pages found for slug='{slug}' and parent={parent_id}. Clean duplicates in WP.")
    return matches[0] if matches else None


def ensure_language_root(pages_api: str, auth: HTTPBasicAuth, lang: str) -> int:
    """
    Ensure top-level page exists with slug == lang (e.g. "de"), parent == 0.
    Returns its page ID.
    """
    lang = lang.strip().lower()
    existing = find_page_by_slug_and_parent(pages_api, auth, lang, parent_id=0)
    if existing:
        return int(existing["id"])

    payload = {
        "slug": lang,
        "title": lang.upper(),
        "content": f"<h2>{lang.upper()}</h2><p>Language hub page.</p>",
        "status": "publish",  # root should exist; change to "draft" if you prefer
        "parent": 0,
    }

    r = requests.post(pages_api, json=payload, auth=auth, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Failed to create language root '{lang}': {r.status_code} {r.text}")

    created = r.json()
    return int(created["id"])


def upsert_page(
    *,
    pages_api: str,
    auth: HTTPBasicAuth,
    slug: str,
    parent_id: int,
    title: str,
    html: str,
    status: str,
    meta_description: str = "",
    primary_key_word: str = "",
) -> Tuple[Dict[str, Any], str]:
    existing = find_page_by_slug_and_parent(pages_api, auth, slug, parent_id=parent_id)

    payload: Dict[str, Any] = {
        "slug": slug,
        "title": title,
        "content": html,
        "status": status,
        "parent": parent_id,
    }

    # Optional: store meta_description as excerpt (works even without RankMath)
    if meta_description.strip():
        payload["excerpt"] = meta_description.strip()

    # Optional: custom meta field (may be rejected by WP depending on config)
    if primary_key_word.strip():
        payload["meta"] = {"ab_primary_key_word": primary_key_word.strip()}

    if existing:
        page_id = existing["id"]
        r = requests.post(f"{pages_api}/{page_id}", json=payload, auth=auth, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Update failed for slug='{slug}' parent={parent_id}: {r.status_code} {r.text}")
        return r.json(), "updated"

    r = requests.post(pages_api, json=payload, auth=auth, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Create failed for slug='{slug}' parent={parent_id}: {r.status_code} {r.text}")
    return r.json(), "created"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.getenv("SITE_KEY", "default"))
    ap.add_argument("--lang", default=None, help="Language folder under drafts/<site>/<lang> (default: site default)")
    ap.add_argument("--status", default="draft", choices=["draft", "publish"])
    ap.add_argument("--dir", default="drafts")
    ap.add_argument("--env_dir", default="sites", help="Directory containing per-site env files (default: sites/)")
    args = ap.parse_args()

    # Load site-specific WP creds (override anything already loaded)
    site_env_path = Path(args.env_dir) / f"{args.site}.env"
    load_dotenv(dotenv_path=site_env_path, override=True)

    site = load_site_config(args.site)
    lang = (args.lang or site.default_language or "en").strip().lower()

    wp_base = os.getenv("WP_BASE_URL", "").strip()
    wp_user = os.getenv("WP_USERNAME", "").strip()
    wp_pass = os.getenv("WP_APP_PASSWORD", "").strip()
    if not wp_base or not wp_user or not wp_pass:
        raise SystemExit(f"Missing WP_BASE_URL, WP_USERNAME, WP_APP_PASSWORD in {site_env_path}.")

    auth = HTTPBasicAuth(wp_user, wp_pass)
    pages_api = wp_pages_api(wp_base)

    drafts_dir = Path(args.dir) / site.site_key / lang
    if not drafts_dir.exists():
        raise SystemExit(f"Drafts directory not found: {drafts_dir}")

    # Determine parent: EN top-level; non-EN under /<lang>/
    parent_id = 0
    if lang != "en":
        parent_id = ensure_language_root(pages_api, auth, lang)

    for path in sorted(drafts_dir.glob("*.json")):
        # ✅ Skip manifest files so they are never published
        if path.name.startswith("_manifest"):
            continue

        with open(path, encoding="utf-8") as f:
            draft = json.load(f)

        # Safety check (prevents cross-site accidents)
        draft_site = (draft.get("site_key") or "").strip()
        if draft_site and draft_site != site.site_key:
            print(f"[WARN] Skip draft from different site ({draft_site}): {path}")
            continue

        slug = (draft.get("slug") or path.stem).strip()
        title = (draft.get("title") or slug).strip()
        html = (draft.get("html") or "").strip()

        page, action = upsert_page(
            pages_api=pages_api,
            auth=auth,
            slug=slug,
            parent_id=parent_id,
            title=title,
            html=html,
            status=args.status,
            meta_description=(draft.get("meta_description") or ""),
            primary_key_word=(draft.get("primary_key_word") or ""),
        )

        print(action, f"{lang}/{slug}" if lang != "en" else slug, page.get("link"))



if __name__ == "__main__":
    main()
