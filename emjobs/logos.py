"""Company logos: a small PNG per domain in site/logos/, fetched once when missing.

    python -m emjobs.logos      # download the logos of newly added companies
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import requests

from .config import ROOT, load_sources

LOGOS = ROOT / "site" / "logos"
PNG = b"\x89PNG\r\n\x1a\n"


def fetch(domain: str, session: requests.Session) -> bool:
    """Save the company's site icon as logos/<domain>.png. Only the domain is sent."""
    target = LOGOS / f"{domain}.png"
    if target.is_file():
        return True
    try:
        response = session.get("https://www.google.com/s2/favicons", params={"domain": domain, "sz": "128"},
                               timeout=(8, 20))
        response.raise_for_status()
    except requests.RequestException:
        return False
    data = response.content
    # The service answers a generic globe (16 px) for unknown domains: keep initials then.
    if not data.startswith(PNG) or len(data) < 600 or len(data) > 200_000:
        return False
    try:
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    except ValueError:
        return False
    if width < 32 or height < 32:
        return False
    LOGOS.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return True


def fetch_missing() -> tuple[int, int]:
    domains = sorted({s.domain for s in load_sources() if s.domain})
    with requests.Session() as session:
        found = sum(fetch(domain, session) for domain in domains)
    return found, len(domains)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    found, total = fetch_missing()
    print(f"Logos disponibles : {found}/{total}")
