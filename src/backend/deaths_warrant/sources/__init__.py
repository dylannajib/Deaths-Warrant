"""Builders that turn published source tables into committed model data.

Each module downloads its source into the git-ignored ``data/`` cache, then writes a small
JSON file under ``src/models``. They run by hand when a source is updated, never in CI, so
committed data is reproducible without the site ever fetching anything at runtime.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CACHE = REPO / "data" / "sources"
USER_AGENT = "deaths-warrant-source-builder (+https://github.com/dylannajib/Deaths-Warrant)"


def fetch(url: str, name: str, *, refresh: bool = False) -> Path:
    """Download ``url`` (https only) to the cache once and return the cached path."""
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https source {url}")
    path = CACHE / name
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - https enforced above
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - https only
            path.write_bytes(response.read())
    return path
