"""Build the static Em Jobs site in an empty directory.

    python -m emjobs.build --collect --output _site      # live collection
    python -m emjobs.build --from offers.json --output _site   # offline preview
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from .collect import Offer, collect
from .config import ROOT, load_criteria, load_sources
from .dates import display_day, display_start
from .safety import assert_public, public_url, validate_snapshot

SITE = ROOT / "site"
ASSETS = ("index.html", "site.css", "app.js", "sources.js", "em-logo.svg", "og-image.png",
          "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png")
VERSIONED = ("site.css", "app.js", "sources.js", "em-logo.svg")


def site_links() -> tuple[str, str]:
    """Public site URL and repository URL, from GitHub Actions or SITE_URL/REPO_URL."""
    repository = os.getenv("GITHUB_REPOSITORY", "")
    site = os.getenv("SITE_URL", "")
    repo = os.getenv("REPO_URL", "")
    if re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", repository):
        owner, name = repository.split("/")
        site = site or f"https://{owner.lower()}.github.io/{name}/"
        repo = repo or f"https://github.com/{repository}"
    return site, repo


def logo_for(domain: str) -> str:
    path = SITE / "logos" / f"{domain}.png"
    if domain and path.is_file() and not path.is_symlink() and path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        return f"logos/{path.name}"
    return ""


def record(offer: Offer, logos: dict[str, str]) -> dict:
    countries = {place.city: place.country for place in load_criteria().places}
    return {
        "title": offer.title, "company": offer.company, "sector": offer.sector,
        "kind": offer.kind, "family": offer.family, "cities": list(offer.cities),
        "location": " / ".join(f"{city} · {countries.get(city, '')}".rstrip(" ·") for city in offer.cities),
        "location_source": offer.location_source or "Non précisé",
        "url": public_url(offer.url), "published": offer.published,
        "date_label": ("Détectée le " if offer.published_inferred else "Publiée le ") + display_day(offer.published),
        "start": display_start(offer.start), "start_month": offer.start if offer.start != "asap" else "",
        "score": offer.score, "logo": logos.get(offer.company) or logos.get(offer.source, ""), "ai": offer.ai,
        "source": offer.source or offer.company,
    }


def previous_snapshot(url: str) -> list[dict]:
    if not url:
        return []
    try:
        response = requests.get(url, timeout=(8, 20), headers={"Cache-Control": "no-cache"})
        response.raise_for_status()
        data = response.json()
        validate_snapshot(data)
        return data["offers"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        logging.warning("Snapshot précédent illisible (%s) : collecte sans historique", type(error).__name__)
        return []


def build(output: Path, *, offers: list[Offer], checks: dict[str, dict]) -> int:
    if output.exists() and any(output.iterdir()):
        raise ValueError("Le dossier de sortie doit être vide")
    if not offers:
        raise ValueError("Aucune offre : l'ancien site est conservé")
    sources = load_sources()
    logos = {source.name: logo_for(source.domain) for source in sources}
    updated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot = {
        "updated": updated,
        "sources": {"checked": len(checks),
                    "unavailable": sum(c["status"] == "error" for c in checks.values()),
                    "retained": sum(c["status"] == "retained" for c in checks.values())},
        "offers": [record(offer, logos) for offer in offers],
    }
    validate_snapshot(snapshot)
    offers_bytes = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
    assert_public(offers_bytes, "offers.json")
    site_url, repo_url = site_links()
    catalog = {"updated": updated, "repository": repo_url, "sources": [
        {"name": s.name, "sector": s.sector, "url": s.board_url, "logo": logos[s.name], "ai": s.ai,
         "count": int(checks.get(s.name, {}).get("count", 0))} for s in sorted(sources, key=lambda s: s.name.casefold())]}
    catalog_bytes = json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode()
    assert_public(catalog_bytes, "sources.json")

    files = {name: SITE / name for name in ASSETS}
    files.update({logo: SITE / logo for logo in logos.values() if logo})
    for name, path in files.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Fichier public manquant ou invalide : {name}")
        assert_public(path.read_bytes(), name)
    output.mkdir(parents=True, exist_ok=True)
    for name, path in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name != "index.html":
            shutil.copyfile(path, target)
            continue
        document = path.read_text(encoding="utf-8")
        for asset in VERSIONED:
            version = hashlib.sha256(files[asset].read_bytes()).hexdigest()[:12]
            document = document.replace(f'"{asset}"', f'"{asset}?v={version}"')
        lines = document.splitlines(keepends=True)
        if not site_url:
            lines = [line for line in lines if "{{SITE_URL}}" not in line]
        if not repo_url:
            lines = [line for line in lines if "{{REPO_URL}}" not in line]
        document = "".join(lines).replace("{{SITE_URL}}", site_url).replace("{{REPO_URL}}", repo_url)
        assert_public(document.encode(), name)
        target.write_text(document, encoding="utf-8")
    (output / "offers.json").write_bytes(offers_bytes)
    (output / "sources.json").write_bytes(catalog_bytes)
    (output / ".nojekyll").touch()
    return len(snapshot["offers"])


def offers_from_snapshot(path: Path) -> tuple[list[Offer], dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_snapshot(data)
    sources = {s.name: s for s in load_sources()}
    offers = [Offer(title=r["title"], company=r["company"], sector=r["sector"], kind=r["kind"], family=r["family"],
                    cities=tuple(r["cities"]), location_source=r["location_source"], url=r["url"],
                    published=r["published"], published_inferred=r["date_label"].startswith("Détectée"),
                    start="asap" if r["start"] == "Dès que possible" else r["start_month"], score=r["score"],
                    ai=r["ai"], source=r["source"]) for r in data["offers"] if r["source"] in sources]
    return offers, {name: {"status": "ok", "count": sum(o.source == name for o in offers)} for name in sources}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--collect", action="store_true", help="interroger les sites carrière")
    group.add_argument("--from", dest="snapshot", type=Path, help="reconstruire depuis un offers.json")
    parser.add_argument("--previous", default=os.getenv("PREVIOUS_OFFERS_URL", ""),
                        help="offers.json publié, pour conserver les dates et les offres des sources en panne")
    args = parser.parse_args(argv)
    if args.collect:
        offers, checks = collect(previous_snapshot(args.previous))
        for name, check in sorted(checks.items()):
            if check["status"] != "ok":
                print(f"Source {name} : {check['status']} ({check.get('error', '')})", flush=True)
    else:
        offers, checks = offers_from_snapshot(args.snapshot)
    count = build(args.output, offers=offers, checks=checks)
    print(f"Site Em Jobs construit : {count} offres, {len(checks)} sources", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
