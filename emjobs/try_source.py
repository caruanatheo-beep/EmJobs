"""Try companies before adding them to config/sources.toml. Nothing is published.

    python -m emjobs.try_source ashby:doctolib lever:theodo
    python -m emjobs.try_source "workday:sanofi.wd3.myworkdayjobs.com/sanofi/SanofiCareers"

Prints, for each board, how many postings it lists, how many are in Paris or
London, and the offers Em Jobs would keep with today's criteria.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import requests

from .classify import cities
from .collect import offers_from
from .config import Source, load_criteria
from .connectors import CONNECTORS


def try_board(ats: str, slug: str) -> str:
    criteria = load_criteria()
    source = Source(slug, ats, slug, "test")
    try:
        raw = CONNECTORS[ats](source, requests.Session())
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        status = getattr(getattr(error, "response", None), "status_code", "")
        return f"✗ {ats}:{slug} — illisible ({type(error).__name__} {status})".rstrip()
    local = sum(bool(cities(job.locations, criteria)) for job in raw)
    kept = offers_from(source, raw, criteria=criteria, today=datetime.now(timezone.utc).date(), first_seen={})
    lines = [f"✓ {ats}:{slug} — {len(raw)} annonces, dont {local} à Paris/Londres, {len(kept)} retenue(s)"]
    lines += [f"    {offer.kind:8} {offer.family:28} {offer.title}" for offer in kept]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page.
    boards = [item.strip() for arg in argv for item in arg.split(",") if item.strip()]
    if not boards or any(":" not in board or board.split(":", 1)[0] not in CONNECTORS for board in boards):
        print(__doc__)
        print("Outils possibles :", ", ".join(sorted(CONNECTORS)))
        return 2
    for board in boards:
        ats, slug = board.split(":", 1)
        print(try_board(ats, slug), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
