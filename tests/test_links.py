"""Link-only career sites are listed on the Entreprises tab but never collected."""
import json

from emjobs import build as site, collect as collector
from emjobs.collect import Offer
from emjobs.config import Source, load_sources


def test_link_only_sources_are_not_collected(monkeypatch):
    called = []
    monkeypatch.setitem(collector.CONNECTORS, "ashby", lambda source, session: called.append(source) or [])
    link = Source("Groupe", "lien", "https://careers.example.com/fr", "Grands groupes", "example.com")
    startup = Source("Startup", "ashby", "startup", "IA")
    _, checks = collector.collect(sources=(link, startup))
    assert [s.name for s in called] == ["Startup"] and "Groupe" not in checks
    assert link.board_url == "https://careers.example.com/fr" and not link.collected


def test_link_only_sources_appear_in_the_catalog(tmp_path):
    links = [s for s in load_sources() if s.ats == "lien"]
    assert links, "au moins un grand groupe en lien direct"
    offer = Offer("Product Manager Intern", load_sources()[0].name, "IA", "Stage", "Product Management", ("Paris",),
                  "Paris", "https://job-boards.greenhouse.io/example/jobs/1", "2026-11-20", False, "", 80)
    site.build(tmp_path / "out", offers=[offer], checks={})
    catalog = json.loads((tmp_path / "out" / "sources.json").read_text(encoding="utf-8"))
    listed = {s["name"]: s for s in catalog["sources"]}
    assert all(listed[s.name]["link_only"] and listed[s.name]["url"].startswith("https://") for s in links)
