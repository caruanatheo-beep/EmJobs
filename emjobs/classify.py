"""Decide whether a public posting is an early-career product role in Paris or London."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from .config import Criteria, load_criteria


def normalize(value: str, *, keep_case: bool = False) -> str:
    """Accent-free words separated by single spaces, for whole-word matching."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    if not keep_case:
        text = text.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]+", " ", text)).strip()


def _case_sensitive(expression: str) -> bool:
    """An expression written in CAPITALS (e.g. "VIE") must appear in capitals."""
    return expression.upper() == expression and any(char.isalpha() for char in expression)


@lru_cache(maxsize=4096)
def _pattern(expression: str) -> re.Pattern:
    words = normalize(expression, keep_case=_case_sensitive(expression))
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(words)}(?![A-Za-z0-9])")


def contains(text: str, expressions) -> str:
    """Return the first expression found as whole words in ``text``, or ''."""
    lower, cased = normalize(text), normalize(text, keep_case=True)
    for expression in expressions:
        if _pattern(expression).search(cased if _case_sensitive(expression) else lower):
            return expression
    return ""


# Normalised text: "3+ years of relevant experience" -> "3 years of relevant experience".
_YEARS = re.compile(
    r"(?<![a-z0-9])(\d{1,2})(?: (?:to |a )?\d{1,2})? (?:years?|yrs?|ans|annees)(?![a-z0-9])"
    r"(?: [a-z]+){0,6}? (?:experience|work|professional|relevant|industry)(?![a-z0-9])"
)


def minimum_years(description: str) -> int | None:
    """Smallest explicit experience requirement in the description (None if absent)."""
    values = [int(match.group(1)) for match in _YEARS.finditer(normalize(description))]
    values = [value for value in values if value <= 15]
    return min(values) if values else None


@dataclass(frozen=True)
class Match:
    kind: str
    family: str
    cities: tuple[str, ...]


def cities(locations: list[str], criteria: Criteria | None = None) -> tuple[str, ...]:
    criteria = criteria or load_criteria()
    return tuple(place.city for place in criteria.places
                 if any(contains(location, place.expressions) for location in locations if location))


def classify(title: str, locations: list[str], *, employment: str = "", description: str = "",
             criteria: Criteria | None = None) -> Match | None:
    criteria = criteria or load_criteria()
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        return None
    internship_words = dict(criteria.kinds).get("Stage", ())
    # Boards often file internships under "Apprenticeship / Internship": the
    # contract field excludes a posting only when it does not also say internship.
    excluded_contract = contains(employment, criteria.excluded_contracts) and not contains(employment, internship_words)
    if (contains(title, criteria.seniority) or contains(title, criteria.excluded_roles)
            or contains(title, criteria.excluded_contracts) or excluded_contract):
        return None
    family = next((f.name for f in criteria.families if contains(title, f.expressions)), "")
    if not family:
        return None
    found = cities(locations, criteria)
    if not found:
        return None
    kind = next((name for name, expressions in criteria.kinds if contains(title, expressions)), "")
    if not kind:
        # Employer contract fields are trusted only for internships and VIE.
        kind = next((name for name, expressions in criteria.kinds
                     if name in {"Stage", "VIE"} and contains(employment, expressions)), "")
    years = minimum_years(description)
    if not kind and (years is not None and years <= criteria.junior_max_years
                     or years is None and contains(description, criteria.junior_hints)):
        kind = "Junior"
    if not kind:
        return None
    if kind in {"Graduate", "Junior"} and years is not None and years > criteria.junior_max_years:
        return None
    return Match(kind, family, found)


def score(match: Match, *, ai: bool, age_days: int | None, criteria: Criteria | None = None) -> int:
    """Relevance out of 100: role up to 40, contract up to 30, AI focus 10, freshness up to 20."""
    criteria = criteria or load_criteria()
    weight = next((f.weight for f in criteria.families if f.name == match.family), 0)
    freshness = 20 if age_days is None else max(0, 20 - age_days // 3)
    return min(100, weight + criteria.kind_weights.get(match.kind, 20) + (10 if ai else 0) + freshness)
