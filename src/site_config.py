import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class SiteConfig:
    site_key: str
    city: str
    languages: List[str]
    default_language: str


def _split_langs(value: str) -> List[str]:
    langs = [x.strip().lower() for x in (value or "").split(",") if x.strip()]
    return langs or ["en"]


def load_site_env(site_key: str) -> None:
    """Load sites/<site_key>.env if present (overrides project .env)."""
    env_path = Path("sites") / f"{site_key}.env"
    if env_path.exists():
        load_dotenv(env_path, override=True)


def load_site_config(site_key: Optional[str] = None) -> SiteConfig:
    site_key = (site_key or os.getenv("SITE_KEY") or "default").strip()
    load_site_env(site_key)

    city = (os.getenv("CITY") or "").strip() or site_key.title()
    languages = _split_langs(os.getenv("LANGUAGES") or "en")

    default_language = (os.getenv("DEFAULT_LANGUAGE") or languages[0] or "en").strip().lower()
    if default_language not in languages:
        languages = [default_language] + [l for l in languages if l != default_language]

    return SiteConfig(
        site_key=site_key,
        city=city,
        languages=languages,
        default_language=default_language,
    )


def site_input_path(site_key: str, relative: str) -> Path:
    """Return input/<site_key>/<relative> if it exists, else input/<relative>."""
    p1 = Path("input") / site_key / relative
    if p1.exists():
        return p1
    return Path("input") / relative
