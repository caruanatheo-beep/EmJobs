"""The editable files in config/ must stay valid: these tests run before every publication."""
from emjobs.config import ATS, KINDS, load_criteria, load_sources


def test_sources_load_and_are_unique():
    sources = load_sources()
    assert len(sources) >= 20
    assert len({s.name.casefold() for s in sources}) == len(sources)
    assert all(s.ats in ATS and s.sector for s in sources)


def test_every_source_has_a_public_https_board():
    for source in load_sources():
        assert source.board_url.startswith("https://"), source.name


def test_criteria_cover_paris_london_and_every_contract():
    criteria = load_criteria()
    assert {place.city for place in criteria.places} >= {"Paris", "Londres"}
    assert {name for name, _ in criteria.kinds} == set(KINDS)
    assert criteria.families and all(f.weight > 0 for f in criteria.families)
