import argparse
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_CSS_PATH = Path("assets/global.css")


def _auth_session(user: str, password: str) -> requests.Session:
    s = requests.Session()
    s.auth = (user, password)  # basic auth (works if your site has it enabled)
    s.headers.update({"User-Agent": "ApartmentBudapestCSSPublisher/1.0"})
    return s


def detect_stylesheet_slug(base_url: str, s: requests.Session) -> Optional[str]:
    """
    Tries to discover the active theme stylesheet slug.
    This is the most reliable *if* your WP exposes /wp/v2/settings.
    """
    api = base_url.rstrip("/") + "/wp-json/wp/v2"
    r = s.get(f"{api}/settings", timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    # Some sites expose 'stylesheet' in settings. Others don't.
    return data.get("stylesheet") or data.get("template")


def get_custom_css_rest_base(base_url: str, s: requests.Session) -> str:
    """
    Confirm custom_css type exists and get its rest_base.
    """
    api = base_url.rstrip("/") + "/wp-json/wp/v2"
    r = s.get(f"{api}/types/custom_css", timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("rest_base") or "custom_css"


def find_custom_css_post(base_url: str, s: requests.Session, rest_base: str, stylesheet: str) -> Optional[Dict[str, Any]]:
    """
    Finds the custom_css post for a specific stylesheet (slug == stylesheet).
    """
    api = base_url.rstrip("/") + "/wp-json/wp/v2"
    r = s.get(
        f"{api}/{rest_base}",
        params={"search": stylesheet, "per_page": 100},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json()
    for item in items:
        if item.get("slug") == stylesheet:
            return item
    return None


def upsert_additional_css(base_url: str, user: str, password: str, css_text: str, stylesheet: str) -> Tuple[str, int]:
    """
    Updates/creates the Additional CSS entry for the given theme stylesheet slug.
    Returns: ("updated"|"created", post_id)
    """
    s = _auth_session(user, password)
    rest_base = get_custom_css_rest_base(base_url, s)
    api = base_url.rstrip("/") + "/wp-json/wp/v2"

    payload = {
        "title": f"Additional CSS ({stylesheet})",
        "content": css_text,
        "status": "publish",
        "slug": stylesheet,
    }

    existing = find_custom_css_post(base_url, s, rest_base, stylesheet)
    if existing:
        post_id = existing["id"]
        r = s.post(f"{api}/{rest_base}/{post_id}", json=payload, timeout=30)
        r.raise_for_status()
        return ("updated", post_id)

    r = s.post(f"{api}/{rest_base}", json=payload, timeout=30)
    r.raise_for_status()
    return ("created", r.json()["id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", help="e.g. https://apartmentbratislava.com", required=False)
    ap.add_argument("--css", help="Path to CSS file", default=str(DEFAULT_CSS_PATH))
    ap.add_argument("--stylesheet", help="Theme stylesheet slug, e.g. generatepress", default=None)
    ap.add_argument("--all", action="store_true", help="Publish CSS to all sites in SITES env var")
    args = ap.parse_args()

    css_path = Path(args.css)
    if not css_path.exists():
        raise SystemExit(f"CSS file not found: {css_path}")

    css_text = css_path.read_text(encoding="utf-8")

    wp_user = os.getenv("WP_USER")
    wp_pass = os.getenv("WP_APP_PASSWORD") or os.getenv("WP_PASSWORD")
    if not wp_user or not wp_pass:
        raise SystemExit("Missing WP_USER and WP_APP_PASSWORD (or WP_PASSWORD) in environment.")

    # Target sites: either one --base-url or --all from env var.
    sites: List[str] = []
    if args.all:
        # Comma-separated list of base URLs in .env: SITES=https://site1.com,https://site2.com
        raw = os.getenv("SITES", "").strip()
        if not raw:
            raise SystemExit("You used --all but SITES is empty/missing in environment.")
        sites = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
    else:
        if not args.base_url:
            raise SystemExit("Provide --base-url or use --all.")
        sites = [args.base_url.strip().rstrip("/")]

    for base_url in sites:
        s = _auth_session(wp_user, wp_pass)

        stylesheet = args.stylesheet
        if not stylesheet:
            stylesheet = detect_stylesheet_slug(base_url, s) or "generatepress"

        try:
            status, post_id = upsert_additional_css(
                base_url=base_url,
                user=wp_user,
                password=wp_pass,
                css_text=css_text,
                stylesheet=stylesheet,
            )
            print(f"[OK] {base_url} -> {status} custom_css id={post_id} (stylesheet={stylesheet})")
        except requests.HTTPError as e:
            resp = e.response
            print(f"[ERROR] {base_url} -> HTTP {resp.status_code}: {resp.text[:400]}")
        except Exception as e:
            print(f"[ERROR] {base_url} -> {e}")


if __name__ == "__main__":
    main()
