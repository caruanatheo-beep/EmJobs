"""Collect every configured source and keep the matching early-career product offers."""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

import requests

from .classify import cities, classify, contains, normalize, score
from .config import Criteria, Source, load_criteria, load_sources
from .connectors import CONNECTORS, RawJob
from .dates import start_month

log = logging.getLogger("emjobs")
MAX_DETAILS_PER_SOURCE = 150
DETAIL_WORKERS = 6
WORKDAY_WORKERS = 4  # Workday clusters rate-limit employers together.


@dataclass
class Offer:
    title: str
    company: str
    sector: str
    kind: str
    family: str
    cities: tuple[str, ...]
    location_source: str
    url: str
    published: str
    published_inferred: bool
    start: str
    score: int
    ai: bool = False
    source: str = ""  # Configured source; differs from company for group boards (BPCE, Crédit Agricole).


def title_candidate(title: str, criteria: Criteria) -> bool:
    """Cheap title-only check before any extra detail request."""
    return bool(title) and not (contains(title, criteria.seniority) or contains(title, criteria.excluded_roles)
                                or contains(title, criteria.excluded_contracts)) \
        and any(contains(title, family.expressions) for family in criteria.families)


def trusted_url(url: str, source: Source) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    allowed = host in source.hosts
    if source.domain and (host == source.domain or host.endswith("." + source.domain)):
        allowed = True
    return parts.scheme == "https" and allowed and not parts.username and not parts.password and port in (None, 443)


def _age(published: str, today: date) -> int | None:
    try:
        return max(0, (today - date.fromisoformat(published)).days)
    except ValueError:
        return None


def offers_from(source: Source, jobs: list[RawJob], *, criteria: Criteria, today: date,
                first_seen: dict[str, str]) -> list[Offer]:
    offers: list[Offer] = []
    candidates = []
    for job in jobs:
        if not title_candidate(job.title, criteria):
            continue
        if job.deadline and job.deadline < today.isoformat():
            continue
        known = [l for l in job.locations if l and l.strip() and not re.search(r"\d+ locations?|lieux", l, re.I)]
        if known and not cities(known, criteria):
            continue  # Located elsewhere: no detail request needed.
        candidates.append(job)
    pending = [job for job in candidates if job.details]
    if len(pending) > MAX_DETAILS_PER_SOURCE:
        log.warning("%s : %s fiches détaillées, limitées à %s", source.name, len(pending), MAX_DETAILS_PER_SOURCE)
        skipped = set(map(id, pending[MAX_DETAILS_PER_SOURCE:]))
        candidates = [job for job in candidates if id(job) not in skipped]
        pending = pending[:MAX_DETAILS_PER_SOURCE]
    # Detail pages are independent: read them a few at a time.
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
        list(pool.map(RawJob.load_details, pending))
    for job in candidates:
        match = classify(job.title, job.locations, employment=job.employment,
                         description=job.description, criteria=criteria)
        if not match or not trusted_url(job.url, source):
            continue
        published = job.published or first_seen.get(job.url, "") or today.isoformat()
        offers.append(Offer(
            title=" ".join(job.title.split()), company=job.company or source.name, sector=source.sector,
            kind=match.kind, family=match.family, cities=match.cities,
            location_source=" / ".join(dict.fromkeys(l.strip() for l in job.locations if l and l.strip()))[:300],
            url=job.url, published=published, published_inferred=not job.published,
            start=start_month(job.title, job.description, today=today),
            score=score(match, ai=source.ai, age_days=_age(published, today), criteria=criteria), ai=source.ai, source=source.name,
        ))
    return offers


def deduplicate(offers: list[Offer]) -> list[Offer]:
    """One card per company, title and cities; keep the earliest publication."""
    kept: dict[tuple, Offer] = {}
    for offer in sorted(offers, key=lambda o: o.published):
        kept.setdefault((offer.company, normalize(offer.title), offer.cities), offer)
    by_url: dict[str, Offer] = {}
    for offer in kept.values():
        by_url.setdefault(offer.url, offer)
    newest_first = sorted(by_url.values(), key=lambda o: o.published, reverse=True)
    return sorted(newest_first, key=lambda o: -o.score)


def collect(previous: list[dict] | None = None, *, sources: tuple[Source, ...] | None = None,
            workers: int = 16) -> tuple[list[Offer], dict[str, dict]]:
    """Return offers and a per-source check. A failing source keeps its previous offers."""
    criteria = load_criteria()
    sources = sources if sources is not None else load_sources()
    today = datetime.now(timezone.utc).date()
    previous = previous or []
    first_seen = {row["url"]: row["published"] for row in previous
                  if isinstance(row, dict) and row.get("url") and row.get("published")}

    def run(source: Source) -> tuple[Source, list[Offer] | None, str]:
        started = time.monotonic()
        session = requests.Session()
        try:
            raw = CONNECTORS[source.ats](source, session)
            found = offers_from(source, raw, criteria=criteria, today=today, first_seen=first_seen)
            log.info("%s : %s annonces lues, %s retenues en %.0f s", source.name, len(raw), len(found),
                     time.monotonic() - started)
            return source, found, ""
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            status = getattr(getattr(error, "response", None), "status_code", "")
            return source, None, f"{type(error).__name__} {status}".strip()
        finally:
            session.close()

    offers: list[Offer] = []
    checks: dict[str, dict] = {}
    # Workday has its own small pool: its clusters rate-limit employers together.
    with ThreadPoolExecutor(max_workers=workers) as pool, ThreadPoolExecutor(max_workers=WORKDAY_WORKERS) as workday:
        futures = [(workday if source.ats == "workday" else pool).submit(run, source) for source in sources]
        for future in futures:
            source, found, error = future.result()
            if found is not None:
                offers.extend(found)
                checks[source.name] = {"status": "ok", "count": len(found)}
                continue
            retained = [_offer_from_record(row, source) for row in previous
                        if (row.get("source") or row.get("company")) == source.name]
            retained = [offer for offer in retained if offer]
            offers.extend(retained)
            checks[source.name] = {"status": "retained" if retained else "error", "count": len(retained), "error": error}
            log.warning("%s indisponible (%s) : %s offre(s) précédente(s) conservée(s)", source.name, error, len(retained))
    return deduplicate(offers), checks


def _offer_from_record(row: dict, source: Source) -> Offer | None:
    try:
        return Offer(title=row["title"], company=row["company"], sector=source.sector, kind=row["kind"],
                     family=row["family"], cities=tuple(row["cities"]), location_source=row.get("location_source", ""),
                     url=row["url"], published=row["published"], published_inferred=row["date_label"].startswith("Détectée"),
                     start="asap" if row.get("start") == "Dès que possible" else row.get("start_month", ""),
                     score=int(row.get("score", 0)), ai=source.ai, source=source.name)
    except (KeyError, TypeError, ValueError):
        return None
