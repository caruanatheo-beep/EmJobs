import pytest

from emjobs.classify import classify, minimum_years

PARIS, LONDON = ["Paris, France"], ["London, United Kingdom"]


@pytest.mark.parametrize("title, kind, family", [
    ("Product Manager Intern", "Stage", "Product Management"),
    ("Stage - Product Owner (F/H)", "Stage", "Product Management"),
    ("Product Designer, Internship", "Stage", "Design & UX Research"),
    ("UX Researcher Intern", "Stage", "Design & UX Research"),
    ("Growth Marketing Intern", "Stage", "Growth & Strategy"),
    ("Stage - Strategy & Operations (x/f/m) - mars 2027", "Stage", "Growth & Strategy"),
    ("Stage Assistant(e) Chef de produit", "Stage", "Product Marketing & Chef de produit"),
    ("Product Analyst Intern", "Stage", "Product Ops & Analytics"),
    ("Stage Produit & Partenariats", "Stage", "Produit (autres)"),
    ("Associate Product Manager", "Graduate", "Product Management"),
    ("Graduate Product Designer 2027", "Graduate", "Design & UX Research"),
    ("Junior Product Owner", "Junior", "Product Management"),
    ("VIE - Product Owner", "VIE", "Product Management"),
])
def test_early_career_product_roles_are_kept(title, kind, family):
    match = classify(title, PARIS)
    assert match and (match.kind, match.family) == (kind, family)


@pytest.mark.parametrize("title", [
    "Senior Product Manager",
    "Staff Product Designer",
    "Product Security Engineer Intern",
    "Software Engineer Intern",
    "Product Manager Apprentice, Checkout",
    "Account Executive Product - Fraud & Risk",
    "Legal Intern - Product & Compliance",
    "Data Scientist Internship",
    "Product Manager Assurance vie",  # « vie » en minuscules n'est pas un VIE
])
def test_other_roles_are_excluded(title):
    assert classify(title, PARIS) is None


def test_only_paris_and_london():
    assert classify("Product Manager Intern", ["Berlin, Germany"]) is None
    assert classify("Product Manager Intern", LONDON).cities == ("Londres",)
    assert classify("Product Intern", ["La Défense, France", "London"]).cities == ("Paris", "Londres")


def test_plain_title_uses_the_experience_required():
    assert classify("Product Manager", PARIS, description="1-2 years of experience").kind == "Junior"
    assert classify("Product Manager", PARIS, description="5+ years of product experience") is None
    assert classify("Associate Product Manager", PARIS, description="3+ years of relevant experience") is None
    assert classify("Product Manager", PARIS, description="Great team, Paris office") is None


def test_employer_contract_field_marks_internships():
    assert classify("Product Marketing Manager", PARIS, employment="Intern").kind == "Stage"


def test_minimum_years():
    assert minimum_years("at least 3+ years of relevant product experience") == 3
    assert minimum_years("2-4 ans d'expérience") == 2
    assert minimum_years("founded 10 years ago") is None
