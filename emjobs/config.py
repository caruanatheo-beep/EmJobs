"""Load and validate the editable TOML configuration in ``config/``."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
ATS = {"greenhouse", "lever", "ashby", "smartrecruiters", "workday", "oracle", "successfactors",
       "teamtailor", "workable", "recruitee", "socgen", "bpce", "talentsoft", "avature", "cagroup", "lien"}
_HOST = r"[a-z0-9-]+(?:\.[a-z0-9-]+)+"
_SLUG = {
    # "lien": a career site listed on the Entreprises tab but not collected (slug = its https address).
    "lien": r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[A-Za-z0-9._~%/?=&#-]*)?",
    "socgen": _HOST, "talentsoft": _HOST, "cagroup": _HOST,
    "avature": r"[a-z0-9-]+\.avature\.net/[A-Za-z0-9_-]+",
    "workday": r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+",
    "oracle": r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.oraclecloud\.(?:com|eu)/[A-Za-z0-9_-]+",
    "successfactors": r"[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[A-Za-z0-9_-]+)*",
    "teamtailor": r"[a-z0-9-]+(?:\.[a-z0-9-]+)*",
}
KINDS = ("Stage", "VIE", "Graduate", "Junior")


class ConfigError(ValueError):
    """A human-readable configuration problem, shown in the GitHub Actions log."""


@dataclass(frozen=True)
class Source:
    name: str
    ats: str
    slug: str
    sector: str
    domain: str = ""
    ai: bool = False

    @property
    def collected(self) -> bool:
        """False for link-only career sites, which Em Jobs cannot read automatically."""
        return self.ats != "lien"

    @property
    def board_url(self) -> str:
        if self.ats == "lien":
            return self.slug
        if self.ats == "greenhouse":
            return f"https://job-boards.greenhouse.io/{self.slug}"
        if self.ats == "lever":
            return f"https://jobs.lever.co/{self.slug}"
        if self.ats == "ashby":
            return f"https://jobs.ashbyhq.com/{self.slug}"
        if self.ats == "smartrecruiters":
            return f"https://jobs.smartrecruiters.com/{self.slug}"
        if self.ats == "workday":
            host, _tenant, site = self.slug.split("/")
            return f"https://{host}/{site}"
        if self.ats == "oracle":
            host, site = self.slug.split("/")
            return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/jobs"
        if self.ats == "successfactors":
            return f"https://{self.slug.split('/')[0]}/"
        if self.ats == "teamtailor":
            return f"https://{self.slug if '.' in self.slug else self.slug + '.teamtailor.com'}/jobs"
        if self.ats == "workable":
            return f"https://apply.workable.com/{self.slug}/"
        if self.ats == "socgen":
            return f"https://{self.slug}/en/Technical/all-job-offers"
        if self.ats == "bpce":  # slug: Open Data dataset; offers live on recrutement.bpce.fr
            return "https://recrutement.bpce.fr/offres-emploi"
        if self.ats == "talentsoft":
            return f"https://{self.slug}/offre-de-emploi/liste-offres.aspx"
        if self.ats == "avature":
            return f"https://{self.slug}/SearchJobs/"
        if self.ats == "cagroup":
            return f"https://{self.slug}/fr/nos-offres/"
        return f"https://{self.slug}.recruitee.com/"

    @property
    def hosts(self) -> set[str]:
        """Hosts allowed in this source's offer links, besides the company domain."""
        board = self.board_url.split("/")[2]
        return {board, "jobs.eu.lever.co", "boards.greenhouse.io", "job-boards.eu.greenhouse.io"} \
            if self.ats in {"lever", "greenhouse"} else {board}


@dataclass(frozen=True)
class Place:
    city: str
    country: str
    expressions: tuple[str, ...]


@dataclass(frozen=True)
class Family:
    name: str
    weight: int
    expressions: tuple[str, ...]


@dataclass(frozen=True)
class Criteria:
    places: tuple[Place, ...]
    kinds: tuple[tuple[str, tuple[str, ...]], ...]
    junior_hints: tuple[str, ...]
    junior_max_years: int
    families: tuple[Family, ...]
    seniority: tuple[str, ...]
    excluded_roles: tuple[str, ...]
    excluded_contracts: tuple[str, ...]
    kind_weights: dict[str, int] = field(default_factory=lambda: {
        "Stage": 30, "Graduate": 28, "VIE": 28, "Junior": 24})


def _text_list(value, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        raise ConfigError(f"{where} : une liste d'expressions non vide est attendue, ex. [\"product manager\"]")
    return tuple(v.strip() for v in value)


def _read(name: str) -> dict:
    path = CONFIG_DIR / name
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"config/{name} n'est pas un fichier TOML valide : {error}") from None


@lru_cache(maxsize=1)
def load_sources() -> tuple[Source, ...]:
    data = _read("sources.toml")
    rows = data.get("source")
    if not isinstance(rows, list) or not rows:
        raise ConfigError("config/sources.toml : aucun bloc [[source]] trouvé")
    sources, names = [], set()
    allowed = {"nom", "ats", "slug", "secteur", "domaine", "ia", "actif"}
    for index, row in enumerate(rows, 1):
        where = f"config/sources.toml, source n°{index} ({row.get('nom', '?')})"
        unknown = set(row) - allowed
        if unknown:
            raise ConfigError(f"{where} : champ inconnu {sorted(unknown)} (champs possibles : {sorted(allowed)})")
        for key in ("nom", "ats", "slug", "secteur"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ConfigError(f"{where} : le champ « {key} » est obligatoire")
        ats = row["ats"].strip().lower()
        if ats not in ATS:
            raise ConfigError(f"{where} : ats « {row['ats']} » inconnu (possibles : {', '.join(sorted(ATS))})")
        slug = row["slug"].strip()
        pattern = _SLUG.get(ats, r"[A-Za-z0-9_.-]+")
        if not re.fullmatch(pattern, slug):
            raise ConfigError(f"{where} : slug « {slug} » invalide")
        domain = str(row.get("domaine", "")).strip().lower()
        if domain and not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", domain):
            raise ConfigError(f"{where} : domaine « {domain} » invalide (ex. doctolib.fr)")
        for flag in ("ia", "actif"):
            if flag in row and not isinstance(row[flag], bool):
                raise ConfigError(f"{where} : « {flag} » doit valoir true ou false")
        name = row["nom"].strip()
        if name.casefold() in names:
            raise ConfigError(f"{where} : l'entreprise « {name} » est déjà présente")
        names.add(name.casefold())
        if row.get("actif", True):
            sources.append(Source(name, ats, slug, row["secteur"].strip(), domain, bool(row.get("ia", False))))
    return tuple(sources)


@lru_cache(maxsize=1)
def load_criteria() -> Criteria:
    data = _read("criteres.toml")
    try:
        places = tuple(Place(p["ville"], p["pays"], _text_list(p["expressions"], f"lieu {p['ville']}"))
                       for p in data["lieu"])
        kinds = tuple((k["nom"], _text_list(k["expressions"], f"contrat {k['nom']}")) for k in data["contrat"])
        families = tuple(Family(m["nom"], int(m["poids"]), _text_list(m["expressions"], f"métier {m['nom']}"))
                         for m in data["metier"])
        junior = data["junior_par_description"]
        exclusions = data["exclusions"]
        criteria = Criteria(
            places=places, kinds=kinds,
            junior_hints=_text_list(junior["expressions"], "junior_par_description"),
            junior_max_years=int(junior["annees_max"]),
            families=families,
            seniority=_text_list(exclusions["seniorite"], "exclusions.seniorite"),
            excluded_roles=_text_list(exclusions["metiers"], "exclusions.metiers"),
            excluded_contracts=_text_list(exclusions["contrats"], "exclusions.contrats"),
        )
    except (KeyError, TypeError) as error:
        raise ConfigError(f"config/criteres.toml : section ou champ manquant ({error})") from None
    unknown = {name for name, _ in criteria.kinds} - set(KINDS)
    if unknown:
        raise ConfigError(f"config/criteres.toml : contrat inconnu {sorted(unknown)} (possibles : {', '.join(KINDS)})")
    if not criteria.places or not criteria.families:
        raise ConfigError("config/criteres.toml : au moins un lieu et un métier sont nécessaires")
    return criteria
