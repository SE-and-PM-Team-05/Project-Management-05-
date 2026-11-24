"""SCRUM-87: the allChecksPassed summary (REQ-FUNC-047). Pure rule, no database or source."""

import pytest

from checks.results import all_checks_passed


def entry(check, result):
    return {"check": check, "result": result}


ALL_EXPECTED = [
    entry("vatValid", "TRUE"),
    entry("nameMatchesVat", "TRUE"),
    entry("listedAsFakeCompany", "FALSE"),
    entry("onHfuList", "FALSE"),
    entry("inCompanyRegister", "TRUE"),
    entry("inBusinessLicenseRegister", "TRUE"),
    entry("hasRequiredLicenses", "TRUE"),
]


def replaced(check, result):
    return [entry(check, result) if e["check"] == check else e for e in ALL_EXPECTED]


def test_every_check_with_its_expected_value_passes():
    """REQ-FUNC-047: TRUE where TRUE is expected and FALSE for listedAsFakeCompany gives true."""
    assert all_checks_passed(ALL_EXPECTED) is True


@pytest.mark.parametrize(
    "check, result",
    [
        ("vatValid", "FALSE"),
        ("nameMatchesVat", "FALSE"),
        ("listedAsFakeCompany", "TRUE"),
        ("inCompanyRegister", "FALSE"),
        ("inBusinessLicenseRegister", "FALSE"),
        ("hasRequiredLicenses", "FALSE"),
    ],
)
def test_any_deviating_check_gives_false(check, result):
    """REQ-FUNC-047: one check without its expected value sets the summary to false."""
    assert all_checks_passed(replaced(check, result)) is False


@pytest.mark.parametrize("check", ["vatValid", "listedAsFakeCompany", "inCompanyRegister"])
def test_unknown_gives_false(check):
    """REQ-FUNC-047: UNKNOWN is never a pass, so it sets the summary to false."""
    assert all_checks_passed(replaced(check, "UNKNOWN")) is False


@pytest.mark.parametrize("result", ["TRUE", "FALSE", "UNKNOWN"])
def test_hfu_is_ignored(result):
    """REQ-FUNC-047, REQ-FUNC-034: onHfuList is informational and never changes the summary."""
    assert all_checks_passed(replaced("onHfuList", result)) is True


def test_not_applicable_checks_are_ignored():
    """REQ-FUNC-047, REQ-FUNC-038: NOT_APPLICABLE checks, e.g. Austrian registers for a German partner, are skipped."""
    checks = [entry("vatValid", "TRUE"), entry("nameMatchesVat", "NOT_APPLICABLE")] + [
        entry(name, "NOT_APPLICABLE")
        for name in ("listedAsFakeCompany", "onHfuList", "inCompanyRegister", "inBusinessLicenseRegister")
    ]
    assert all_checks_passed(checks) is True


def test_check_without_an_expected_value_gives_false():
    """REQ-FUNC-047: a check with no expected value yet can't count as passed."""
    assert all_checks_passed(ALL_EXPECTED + [entry("someNewCheck", "TRUE")]) is False
