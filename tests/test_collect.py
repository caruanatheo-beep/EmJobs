"""Collection keeps working when one company's site is down."""
import requests

from emjobs import collect as collector
from emjobs.config import Source
from emjobs.connectors import RawJob

GROUP = Source("Groupe Test", "bpce", "export", "Banque & finance", "example.com")
STARTUP = Source("Startup Test", "ashby", "startup", "IA", "", True)


def test_failing_source_keeps_its_previous_offers(monkeypatch):
    def down(source, session):
        raise requests.ConnectionError("down")

    def up(source, session):
        return [RawJob("Product Manager Intern", ["Paris, France"], "https://jobs.ashbyhq.com/startup/1", "2026-11-20")]

    monkeypatch.setitem(collector.CONNECTORS, "bpce", down)
    monkeypatch.setitem(collector.CONNECTORS, "ashby", up)
    previous = [{"title": "Stage Product Owner", "company": "Filiale A", "source": "Groupe Test", "kind": "Stage",
                 "family": "Product Management", "cities": ["Paris"], "location_source": "Paris",
                 "url": "https://example.com/job/1", "published": "2026-11-01",
                 "date_label": "Publiée le 1 novembre 2026", "start": "Non précisé", "start_month": "", "score": 80}]
    offers, checks = collector.collect(previous, sources=(GROUP, STARTUP))
    assert checks["Groupe Test"]["status"] == "retained"
    assert checks["Startup Test"] == {"status": "ok", "count": 1}
    kept = {offer.company: offer for offer in offers}
    assert kept["Filiale A"].source == "Groupe Test"
    assert kept["Startup Test"].kind == "Stage" and kept["Startup Test"].ai


def test_undated_offer_keeps_its_first_seen_date(monkeypatch):
    monkeypatch.setitem(collector.CONNECTORS, "ashby", lambda source, session: [
        RawJob("Junior Product Owner", ["London"], "https://jobs.ashbyhq.com/startup/2")])
    previous = [{"url": "https://jobs.ashbyhq.com/startup/2", "published": "2026-10-02"}]
    offers, _ = collector.collect(previous, sources=(STARTUP,))
    assert offers[0].published == "2026-10-02" and offers[0].published_inferred
