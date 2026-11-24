"""Fail closed before publishing. Never print a matched credential."""
from __future__ import annotations

import ipaddress
import os
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlsplit

from .config import KINDS

OFFER_FIELDS = {"title", "company", "sector", "kind", "family", "cities", "location", "location_source",
                "url", "published", "date_label", "start", "start_month", "score", "logo", "ai", "source"}

SECRET = re.compile(
    rb"(?:(?<![A-Za-z0-9])sk-(?:proj-|svcacct-|ant-)?[A-Za-z0-9_-]{20,}"
    rb"|AIza[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}"
    rb"|github_pat_[A-Za-z0-9_]{30,}|hf_[A-Za-z0-9]{25,}"
    rb"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)


def assert_public(payload: bytes, label: str) -> None:
    if SECRET.search(payload):
        raise ValueError(f"Publication refusée : possible identifiant secret dans {label}")
    for name, value in os.environ.items():
        if len(value) >= 8 and any(word in name.upper() for word in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
            if value.encode() in payload:
                raise ValueError(f"Publication refusée : variable d'environnement secrète dans {label}")


def public_url(value: str) -> str:
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if (parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443)
            or "." not in host or host.endswith((".local", ".internal")) or host == "localhost"):
        raise ValueError("Publication refusée : lien d'offre invalide")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Publication refusée : adresse IP dans un lien d'offre")
    sensitive = {"key", "api_key", "apikey", "token", "access_token", "secret", "password", "authorization", "signature"}
    if any(name.lower() in sensitive for name, _ in parse_qsl(parts.query)):
        raise ValueError("Publication refusée : paramètre sensible dans un lien d'offre")
    return value


def validate_snapshot(data: dict) -> None:
    if set(data) != {"updated", "sources", "offers"}:
        raise ValueError("Publication refusée : champs inattendus dans offers.json")
    if set(data["sources"]) != {"checked", "unavailable", "retained"} or any(
            type(v) is not int or v < 0 for v in data["sources"].values()):
        raise ValueError("Publication refusée : diagnostic des sources invalide")
    datetime.fromisoformat(data["updated"])
    for record in data["offers"]:
        if set(record) != OFFER_FIELDS:
            raise ValueError("Publication refusée : champs d'offre inattendus")
        if record["kind"] not in KINDS:
            raise ValueError("Publication refusée : type de contrat inconnu")
        if not isinstance(record["cities"], list) or not all(isinstance(c, str) for c in record["cities"]):
            raise ValueError("Publication refusée : villes invalides")
        if type(record["score"]) is not int or type(record["ai"]) is not bool:
            raise ValueError("Publication refusée : score invalide")
        for name in OFFER_FIELDS - {"cities", "score", "ai"}:
            if not isinstance(record[name], str) or len(record[name]) > 1000:
                raise ValueError(f"Publication refusée : champ « {name} » invalide")
        public_url(record["url"])
