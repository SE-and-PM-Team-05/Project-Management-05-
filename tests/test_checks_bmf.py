"""SCRUM-65/66: BMF fake-company check and stale flag. VIES is mocked; the list is in the test database."""

import time
from datetime import UTC, date, datetime, timedelta
from unittest import mock

import pytest

from checks.models import CheckRequestResult, FakeCompany, SyncLog
from checks.results import CheckResult, Partner, utc_now
from checks.sources.bmf import BmfAdapter
from tests.test_checks_api import VALID_INPUT, checks_of, make_user, post, vies_answer

PARTNER = Partner(vat_number="ATU12345678", company_name="Muster Bau GmbH")


def run(partner, deadline=None):
    (result,) = BmfAdapter().run(partner, deadline or time.monotonic() + 8)
    return result


def make_sync(age=timedelta(hours=1), outcome=SyncLog.OUTCOME_SUCCESS):
    end = utc_now() - age
    return SyncLog.objects.create(
        source=SyncLog.SOURCE_BMF, start_time=end - timedelta(seconds=4), end_time=end, outcome=outcome
    )


def make_entry(**fields):
    fields = {"name": "Schein Bau GmbH", "date_listed": date(2026, 11, 4)} | fields
    return FakeCompany.objects.create(**fields)


# --- listedAsFakeCompany (REQ-FUNC-033) ---


def test_req_func_033_vat_match_is_true_with_details(db):
    """Verifies REQ-FUNC-033."""
    sync = make_sync()
    make_entry(vat_number="ATU12345678", company_register_number="123456a", address="Hauptstraße 1, 1010 Wien")
    result = run(PARTNER)
    assert (result.check, result.result, result.source, result.reason) == ("listedAsFakeCompany", "TRUE", "BMF", None)
    assert result.data_timestamp == sync.end_time
    assert result.details == {
        "name": "Schein Bau GmbH",
        "vatNumber": "ATU12345678",
        "companyRegisterNumber": "123456a",
        "address": "Hauptstraße 1, 1010 Wien",
        "dateListed": "2026-11-04",
        "matchedBy": "vatNumber",
    }


def test_req_func_033_empty_fields_are_left_out_of_the_details(db):
    """Verifies REQ-FUNC-033."""
    make_sync()
    make_entry(vat_number="ATU12345678")
    assert run(PARTNER).details == {
        "name": "Schein Bau GmbH",
        "vatNumber": "ATU12345678",
        "dateListed": "2026-11-04",
        "matchedBy": "vatNumber",
    }


def test_req_func_033_fn_match_ignores_case_spaces_and_prefix_when_vat_differs(db):
    """Verifies REQ-FUNC-033."""
    make_sync()
    make_entry(vat_number="ATU99999999", company_register_number="FN 123456 A")
    partner = Partner(vat_number="ATU12345678", company_name="Anders GmbH", company_register_number="123456a")
    result = run(partner)
    assert result.result == "TRUE"
    assert result.details["matchedBy"] == "companyRegisterNumber"


def test_req_func_033_name_only_match_is_ambiguous(db):
    """Verifies REQ-FUNC-033."""
    make_sync()
    make_entry(name="Schein Bau GmbH", vat_number="ATU99999999")
    result = run(Partner(vat_number="ATU12345678", company_name="Schein-Bau G.m.b.H."))
    assert (result.result, result.reason) == ("UNKNOWN", "AMBIGUOUS_MATCH")
    assert result.details == {
        "candidates": [
            {"name": "Schein Bau GmbH", "vatNumber": "ATU99999999", "dateListed": "2026-11-04", "matchedBy": "name"}
        ]
    }
    assert result.stale is False


def test_req_func_033_without_a_name_vat_number_still_matches(db):
    """REQ-FUNC-033: a check with only a VAT number still finds a listed company by its VAT number (SCRUM-93)."""
    make_sync()
    make_entry(vat_number="ATU12345678")
    result = run(Partner(vat_number="ATU12345678"))
    assert (result.result, result.details["matchedBy"]) == ("TRUE", "vatNumber")


def test_req_func_033_without_a_name_fn_still_matches(db):
    """REQ-FUNC-033."""
    make_sync()
    make_entry(vat_number="ATU99999999", company_register_number="123456a")
    result = run(Partner(vat_number="ATU12345678", company_register_number="123456a"))
    assert (result.result, result.details["matchedBy"]) == ("TRUE", "companyRegisterNumber")


def test_req_func_033_without_a_name_there_is_no_name_step(db):
    """REQ-FUNC-033: no name given means no name comparison, so no AMBIGUOUS_MATCH, only FALSE."""
    make_sync()
    make_entry(name="Schein Bau GmbH", vat_number="ATU99999999")
    make_entry(name="", vat_number="ATU88888888")  # an empty normalized name must not match an empty input
    result = run(Partner(vat_number="ATU12345678"))
    assert (result.result, result.reason, result.details) == ("FALSE", None, {})


def test_req_func_033_no_match_is_false(db):
    """Verifies REQ-FUNC-033."""
    make_sync()
    make_entry(vat_number="ATU99999999", company_register_number="999999z")
    result = run(PARTNER)
    assert (result.result, result.reason, result.details) == ("FALSE", None, {})


def test_req_func_033_no_sync_yet_is_unknown_source_unavailable(db):
    """Verifies REQ-FUNC-033."""
    make_entry(vat_number="ATU12345678")
    result = run(PARTNER)
    assert (result.result, result.reason, result.details) == ("UNKNOWN", "SOURCE_UNAVAILABLE", {"error": "NO_SYNC"})
    assert result.stale is None


def test_req_func_073_failed_newer_sync_keeps_using_the_last_success(db):
    """Verifies REQ-FUNC-073."""
    success = make_sync(age=timedelta(hours=30))
    make_sync(age=timedelta(hours=6), outcome=SyncLog.OUTCOME_FAILED)
    make_entry(vat_number="ATU12345678")
    result = run(PARTNER)
    assert result.result == "TRUE"
    assert result.data_timestamp == success.end_time
    assert result.stale is False


# --- stale flag (REQ-FUNC-073) ---


@pytest.mark.parametrize(("hours", "stale"), [(47, False), (49, True)])
def test_req_func_073_stale_after_48_hours(db, hours, stale):
    """Verifies REQ-FUNC-073."""
    make_sync(age=timedelta(hours=hours))
    assert run(PARTNER).stale is stale


# --- applies_to (REQ-FUNC-038) ---


@pytest.mark.parametrize(
    ("vat", "fn", "expected"),
    [("DE123456789", "", False), ("ATU12345678", "", True), ("DE123456789", "123456a", True)],
)
def test_req_func_038_only_austrian_partners_are_checked(vat, fn, expected):
    """Verifies REQ-FUNC-038."""
    assert BmfAdapter().applies_to(Partner(vat, "X GmbH", fn)) is expected


# --- performance (REQ-PERF-002) ---


def test_req_perf_002_name_lookup_in_2000_entries_takes_under_half_a_second(db):
    """Verifies REQ-PERF-002."""
    make_sync()
    FakeCompany.objects.bulk_create(
        FakeCompany(name=f"Firma {i} GmbH", vat_number=f"ATU{i:08d}", date_listed=date(2026, 11, 4))
        for i in range(2000)
    )
    started = time.perf_counter()
    result = run(Partner(vat_number="ATU99999999", company_name="Firma 1999 GmbH"))
    assert time.perf_counter() - started < 0.5
    assert result.reason == "AMBIGUOUS_MATCH"


# --- JSON (REQ-FUNC-073, Appendix B) ---


def test_req_func_073_to_json_has_stale_after_the_timestamp_only_when_set():
    """Verifies REQ-FUNC-073."""
    moment = datetime(2026, 11, 18, 3, 0, 4, tzinfo=UTC)
    with_stale = CheckResult("listedAsFakeCompany", "FALSE", "BMF", moment, stale=False).to_json()
    assert with_stale == {
        "check": "listedAsFakeCompany",
        "result": "FALSE",
        "source": "BMF",
        "dataTimestamp": "2026-11-18T03:00:04Z",
        "stale": False,
    }
    assert list(with_stale)[-2:] == ["dataTimestamp", "stale"]
    assert "stale" not in CheckResult("vatValid", "TRUE", "VIES", moment).to_json()


# --- through the API and the runner's thread pool ---


@pytest.mark.django_db(transaction=True)
def test_req_func_073_api_returns_and_stores_stale(client):
    """Verifies REQ-FUNC-073."""
    make_sync()
    user = make_user(is_request_user=True)
    client.force_login(user)
    with mock.patch("checks.sources.http.requests.post", return_value=vies_answer()):
        response = post(client, VALID_INPUT)
    check = checks_of(response)["listedAsFakeCompany"]
    assert (check["result"], check["source"], check["stale"]) == ("FALSE", "BMF", False)
    assert "stale" not in checks_of(response)["vatValid"]
    assert CheckRequestResult.objects.get(check_name="listedAsFakeCompany").stale is False
