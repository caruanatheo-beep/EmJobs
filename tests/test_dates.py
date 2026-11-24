from datetime import date

import pytest

from emjobs.dates import display_start, start_month, workday_posted

TODAY = date(2026, 11, 24)


@pytest.mark.parametrize("title, description, expected", [
    ("Product Intern", "Date de début : janvier 2027. Durée 6 mois", "2027-01"),
    ("Product Intern", "Stage à pourvoir dès que possible", "asap"),
    ("Summer 2027 Product Intern", "", "2027-06"),
    ("PM Intern", "Start date: September", "2027-09"),
    ("PM Intern", "starting in March 2027 for 6 months", "2027-03"),
    ("Stage Product Owner - Février 2027", "", "2027-02"),
    ("PM Intern", "We were founded in 2015 in Paris", ""),
])
def test_start_month(title, description, expected):
    assert start_month(title, description, today=TODAY) == expected


def test_display():
    assert display_start("2027-01") == "janvier 2027"
    assert display_start("asap") == "Dès que possible"
    assert display_start("") == "Non précisé"


def test_workday_posted():
    assert workday_posted("Posted 3 Days Ago", today=TODAY) == "2026-11-21"
    assert workday_posted("Posted 30+ Days Ago", today=TODAY) == ""
