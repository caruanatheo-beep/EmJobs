"""Start periods and publication dates, as advertised by the employer."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from .classify import normalize

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")
_MONTHS = {
    **{normalize(name): index for index, name in enumerate(MONTHS_FR, 1)},
    **{name: index for index, name in enumerate((
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december"), 1)},
    **{name: index for index, name in enumerate((
        "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)},
    "sept": 9, "janv": 1, "fevr": 2, "avr": 4, "juil": 7,
}
_SEASONS = {"spring": 3, "printemps": 3, "summer": 6, "ete": 6, "autumn": 9, "fall": 9,
            "automne": 9, "winter": 1, "hiver": 1}
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_SEASON = "|".join(_SEASONS)

# Phrases announcing a start date, on normalised text (lower case, no accents).
_LABEL = (r"(?:date de debut(?: du stage| de stage| du contrat)?|debut du stage|debut de stage|"
          r"prise de poste|demarrage|a pourvoir|a partir de|a partir du|des|start date|"
          r"starting date|starting in|starting on|starting from|starts in|starts on|start in|start on|"
          r"beginning in|beginning on|begins in|commencing|available from)")
_START = re.compile(
    rf"(?<![a-z0-9]){_LABEL}(?: (?:le|en|au|of|in|on|from|souhaitee|prevue|the))*"
    rf" (?:(?P<asap>asap|des que possible|immediatement|immediately)"
    rf"|(?:(?P<day>\d{{1,2}}) (?:er |st |nd |rd |th )?)?(?P<month>{_MONTH})(?: (?:\d{{1,2}} )?(?P<year>20\d{{2}}))?)(?![a-z0-9])"
)
_COHORT = re.compile(
    rf"(?<![a-z0-9])(?:(?P<month>{_MONTH})|(?P<season>{_SEASON}))(?: (?:to |a |au )?(?:{_MONTH}))? (?P<year>20\d{{2}})(?![a-z0-9])"
)


def _month(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def start_month(title: str, description: str = "", *, today: date | None = None) -> str:
    """Return 'YYYY-MM', 'asap' or '' when the employer does not state a start date."""
    today = today or datetime.now(timezone.utc).date()
    text = normalize(description)
    for match in _START.finditer(text):
        if match.group("asap"):
            return "asap"
        month = _MONTHS[match.group("month")]
        year = int(match.group("year") or 0)
        if not year:
            # "Start date: September" means the next September.
            year = today.year + (month < today.month)
        if 2020 <= year <= today.year + 3:
            return _month(year, month)
    # A cohort in the title or description: "Summer 2027", "January 2027 Intern".
    for source in (normalize(title), text):
        match = _COHORT.search(source)
        if match:
            month = _MONTHS[match.group("month")] if match.group("month") else _SEASONS[match.group("season")]
            year = int(match.group("year"))
            if today.year - 1 <= year <= today.year + 3:
                return _month(year, month)
    return ""


def display_start(value: str) -> str:
    if value == "asap":
        return "Dès que possible"
    if re.fullmatch(r"20\d{2}-\d{2}", value or ""):
        year, month = value.split("-")
        return f"{MONTHS_FR[int(month) - 1]} {year}"
    return "Non précisé"


def iso_day(value) -> str:
    """Calendar day (YYYY-MM-DD) from an ISO string or a millisecond timestamp."""
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    text = str(value or "").strip()
    try:
        day = date.fromisoformat(text[:10])
    except ValueError:
        return ""
    return day.isoformat() if day <= datetime.now(timezone.utc).date() + timedelta(days=1) else ""


def workday_posted(value: str, *, today: date | None = None) -> str:
    """Workday shows "Posted Today", "Posted Yesterday" or "Posted 3 Days Ago"."""
    today = today or datetime.now(timezone.utc).date()
    text = normalize(value)
    if "today" in text:
        return today.isoformat()
    if "yesterday" in text:
        return (today - timedelta(days=1)).isoformat()
    match = re.search(r"(\d+) days? ago", text)
    if match and "30" not in text.split():
        return (today - timedelta(days=int(match.group(1)))).isoformat()
    return ""


def display_day(value: str) -> str:
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return "date inconnue"
    return f"{day.day} {MONTHS_FR[day.month - 1]} {day.year}"
