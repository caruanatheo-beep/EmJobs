"""The static build publishes only allowlisted public fields and refuses unsafe content."""
import json

import pytest

from emjobs import build as site
from emjobs.collect import Offer, trusted_url
from emjobs.config import load_sources


def offer(**overrides):
    values = dict(title="Product Manager Intern", company=load_sources()[0].name, sector="IA", kind="Stage",
                  family="Product Management", cities=("Paris",), location_source="Paris, France",
                  url="https://job-boards.greenhouse.io/example/jobs/1", published="2026-11-20",
                  published_inferred=False, start="2027-01", score=90, ai=True)
    values.update(overrides)
    return Offer(**values)


def test_build_writes_a_complete_site(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/em-jobs")
    out = tmp_path / "site"
    assert site.build(out, offers=[offer()], checks={"x": {"status": "ok", "count": 1}}) == 1
    data = json.loads((out / "offers.json").read_text(encoding="utf-8"))
    record = data["offers"][0]
    assert record["location"] == "Paris · France"
    assert record["start"] == "janvier 2027" and record["date_label"] == "Publiée le 20 novembre 2026"
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "{{" not in index and "https://someone.github.io/em-jobs/" in index
    assert "https://github.com/someone/em-jobs/issues/new" in index
    assert "site.css?v=" in index
    assert json.loads((out / "sources.json").read_text(encoding="utf-8"))["sources"]


def test_local_preview_without_repository(tmp_path, monkeypatch):
    for name in ("GITHUB_REPOSITORY", "SITE_URL", "REPO_URL"):
        monkeypatch.delenv(name, raising=False)
    out = tmp_path / "site"
    site.build(out, offers=[offer()], checks={})
    assert "{{" not in (out / "index.html").read_text(encoding="utf-8")


def test_refuses_empty_and_unsafe_output(tmp_path):
    with pytest.raises(ValueError):
        site.build(tmp_path / "a", offers=[], checks={})
    with pytest.raises(ValueError):
        site.build(tmp_path / "b", offers=[offer(url="http://example.com/job")], checks={})
    with pytest.raises(ValueError):
        site.build(tmp_path / "c", offers=[offer(title="ghp_" + "a" * 36)], checks={})


def test_offer_links_must_come_from_the_source():
    source = next(s for s in load_sources() if s.ats == "greenhouse")
    assert trusted_url(f"https://job-boards.greenhouse.io/{source.slug}/jobs/1", source)
    assert not trusted_url("https://evil.example/jobs/1", source)
    assert not trusted_url("http://job-boards.greenhouse.io/x/jobs/1", source)
