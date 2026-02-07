import os
import json
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

WP_BASE_URL = os.environ["WP_BASE_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)
PAGES_API = f"{WP_BASE_URL}/wp-json/wp/v2/pages"

def get_page_by_slug(slug: str):
    r = requests.get(
        PAGES_API,
        params={
            "slug": slug,
            "status": "any",      # IMPORTANT: include drafts
            "per_page": 100,
            "context": "edit"     # helps ensure you see editable items
        },
        auth=auth,
        timeout=30
    )
    r.raise_for_status()
    items = r.json()
    if len(items) > 1:
        raise RuntimeError(f"Multiple pages found for slug '{slug}'. Clean duplicates in WP first.")
    return items[0] if items else None


def upsert_page(slug: str, title: str, html: str, status: str = "draft"):
    existing = get_page_by_slug(slug)
    payload = {
        "slug": slug,
        "title": title,
        "content": html,
        "status": status,
    }

    if existing:
        page_id = existing["id"]
        r = requests.post(f"{PAGES_API}/{page_id}", json=payload, auth=auth, timeout=30)
        r.raise_for_status()
        return r.json(), "updated"
    else:
        r = requests.post(PAGES_API, json=payload, auth=auth, timeout=30)
        r.raise_for_status()
        return r.json(), "created"

from pathlib import Path

if __name__ == "__main__":
    for path in Path("drafts").glob("*.json"):
        with open(path, encoding="utf-8") as f:
            draft = json.load(f)

        page, action = upsert_page(
            slug=draft["slug"],
            title=draft["title"],
            html=draft["html"],
            status="draft"
        )
        print(action, draft["slug"], page.get("link"))

