"""SCRUM-24: VIES adapter, name matching and source runner. VIES is always mocked."""

import time
from unittest import mock

import pytest
import requests

from checks import runner
from checks.names import names_match, normalize_company_name
from checks.results import Partner
from checks.sources.base import SourceAdapter
from checks.sources.vies import VIES_URL, ViesAdapter

AT_PARTNER = Partner(vat_number="ATU12345678", company_name="Muster Bau GmbH")
DE_PARTNER = Partner(vat_number="DE123456789", company_name="Beispiel Handel GmbH")


def vies_response(status=200, **body):
    response = mock.Mock(status_code=status)
    response.json.return_value = body
    return response


def valid_answer(name="MUSTER BAU GMBH", address="HAUPTSTRASSE 1, 3500 KREMS"):
    return vies_response(
        countryCode="AT",
        vatNumber="U12345678",
        requestDate="2026-11-02T09:00:00.000Z",
        valid=True,
        requestIdentifier="",
        name=name,
        address=address,
    )


def run_vies(partner, *answers):
    """Run the adapter with requests.post returning (or raising) the given answers in order."""
    with mock.patch("checks.sources.vies.requests.post", side_effect=list(answers)) as post:
        results = ViesAdapter().run(partner, time.monotonic() + 8)
    return {r.check: r for r in results}, post


# --- vatValid (REQ-FUNC-031) ---


def test_req_func_031_valid_at_number_is_true():
    results, post = run_vies(AT_PARTNER, valid_answer())
    assert results["vatValid"].result == "TRUE"
    assert results["vatValid"].source == "VIES"
    assert results["vatValid"].data_timestamp is not None
    # VIES wants the country code and the number separately.
    assert post.call_args.args == (VIES_URL,)
    assert post.call_args.kwargs["json"] == {"countryCode": "AT", "vatNumber": "U12345678"}


def test_req_func_031_valid_de_number_is_true():
    results, post = run_vies(DE_PARTNER, valid_answer(name="---", address="---"))
    assert results["vatValid"].result == "TRUE"
    assert post.call_args.kwargs["json"] == {"countryCode": "DE", "vatNumber": "123456789"}


def test_req_func_031_invalid_number_is_false():
    results, _ = run_vies(AT_PARTNER, vies_response(valid=False, name="---", address="---"))
    assert results["vatValid"].result == "FALSE"
    assert results["nameMatchesVat"].result == "UNKNOWN"
    assert results["nameMatchesVat"].reason == "NO_DETAILS_FOUND"


@pytest.mark.parametrize(
    "answer",
    [
        requests.Timeout(),
        requests.ConnectionError(),
        vies_response(status=503),
    ],
)
def test_req_int_013_vies_down_twice_is_unknown_source_unavailable(answer):
    results, post = run_vies(AT_PARTNER, answer, answer)
    assert post.call_count == 2  # one retry (REQ-REL-003)
    for check in ("vatValid", "nameMatchesVat"):
        assert results[check].result == "UNKNOWN"
        assert results[check].reason == "SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("error", ["MS_UNAVAILABLE", "TIMEOUT", "MS_MAX_CONCURRENT_REQ"])
def test_req_func_031_vies_side_error_is_unknown_without_retry(error):
    answer = vies_response(actionSucceed=False, errorWrappers=[{"error": error, "message": "x"}])
    results, post = run_vies(AT_PARTNER, answer)
    assert post.call_count == 1
    assert results["vatValid"].result == "UNKNOWN"
    assert results["vatValid"].reason == "SOURCE_UNAVAILABLE"
    assert results["vatValid"].details == {"error": error}


def test_req_func_031_unexpected_answer_is_unknown():
    results, _ = run_vies(AT_PARTNER, vies_response(something="else"))
    assert results["vatValid"].result == "UNKNOWN"
    assert results["vatValid"].reason == "SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("failure", [requests.Timeout(), requests.ConnectionError(), vies_response(status=502)])
def test_req_rel_003_transient_failure_then_success_gives_result(failure):
    results, post = run_vies(AT_PARTNER, failure, valid_answer())
    assert post.call_count == 2
    assert results["vatValid"].result == "TRUE"
    assert results["nameMatchesVat"].result == "TRUE"


def test_req_rel_003_no_retry_when_budget_is_used_up():
    with mock.patch("checks.sources.vies.requests.post", side_effect=requests.Timeout()) as post:
        results = ViesAdapter().run(AT_PARTNER, time.monotonic() - 1)
    assert post.call_count == 0
    assert results[0].reason == "SOURCE_UNAVAILABLE"


def test_req_int_013_timeout_passed_to_requests_stays_within_budget():
    _, post = run_vies(AT_PARTNER, valid_answer())
    assert 0 < post.call_args.kwargs["timeout"] <= 8


# --- nameMatchesVat (REQ-FUNC-032) ---


def test_req_func_032_same_name_different_case_is_true():
    results, _ = run_vies(AT_PARTNER, valid_answer(name="MUSTER BAU GMBH"))
    assert results["nameMatchesVat"].result == "TRUE"
    assert results["nameMatchesVat"].details == {"registeredName": "MUSTER BAU GMBH"}


def test_req_func_032_other_company_is_false():
    results, _ = run_vies(AT_PARTNER, valid_answer(name="ANDERE FIRMA GMBH"))
    assert results["nameMatchesVat"].result == "FALSE"
    assert results["nameMatchesVat"].details == {"registeredName": "ANDERE FIRMA GMBH"}


@pytest.mark.parametrize("name", [None, "", "---", "  ---  "])
def test_req_func_032_no_name_from_vies_is_no_details_found(name):
    results, _ = run_vies(DE_PARTNER, valid_answer(name=name))
    assert results["nameMatchesVat"].result == "UNKNOWN"
    assert results["nameMatchesVat"].reason == "NO_DETAILS_FOUND"
    assert results["vatValid"].result == "TRUE"


@pytest.mark.parametrize(
    ("given", "registered"),
    [
        ("Muster Bau GmbH", "MUSTER BAU GMBH"),
        ("Muster Bau", "MUSTER BAU GMBH"),
        ("Muster-Bau GmbH", "MUSTER BAU G.m.b.H."),
        ("Muster Bau GmbH & Co KG", "MUSTER BAU GMBH & CO. KG"),
        ("Muster Bau Ges.m.b.H.", "Muster Bau GesmbH"),
        ("Huber e.U.", "HUBER EU"),
        ("Straßenbau Huber OG", "STRASSENBAU HUBER"),
        ("  Muster   Bau  AG ", "Muster Bau"),
    ],
)
def test_req_func_032_case_punctuation_and_legal_form_are_ignored(given, registered):
    assert names_match(given, registered)


@pytest.mark.parametrize(
    ("given", "registered"),
    [
        ("Muster Bau GmbH", "Muster Hochbau GmbH"),
        ("Muster Bau GmbH", "Bau Muster GmbH"),
        ("Müller Bau", "MUELLER BAU"),  # no transliteration, documented in checks/names.py
    ],
)
def test_req_func_032_different_names_do_not_match(given, registered):
    assert not names_match(given, registered)


def test_req_func_032_name_that_is_only_a_legal_form_is_kept():
    assert normalize_company_name("AG") == "ag"


# --- Runner (REQ-FUNC-039, REQ-INT-013, REQ-REL-001) ---


class SlowAdapter(SourceAdapter):
    source = "SLOW"
    checks = ("slowCheck",)

    def run(self, partner, deadline):
        time.sleep(2)
        return []


class BrokenAdapter(SourceAdapter):
    source = "BROKEN"
    checks = ("brokenCheck",)

    def run(self, partner, deadline):
        raise RuntimeError("bug in adapter")


class AustriaOnlyAdapter(SourceAdapter):
    source = "AT_ONLY"
    checks = ("austrianCheck",)

    def applies_to(self, partner):
        return partner.country_code == "AT"

    def run(self, partner, deadline):
        raise AssertionError("must not run for non-Austrian partners")


def test_req_int_013_source_that_never_answers_is_unknown_within_budget(monkeypatch):
    monkeypatch.setattr(runner, "SOURCE_TIME_BUDGET", 0.2)
    started = time.monotonic()
    results = runner.run_checks(AT_PARTNER, adapters=[SlowAdapter()])
    assert time.monotonic() - started < 1
    assert results[0].result == "UNKNOWN"
    assert results[0].reason == "SOURCE_UNAVAILABLE"
    assert results[0].source == "SLOW"


def test_req_func_039_failing_source_does_not_stop_the_others():
    with mock.patch("checks.sources.vies.requests.post", return_value=valid_answer()):
        results = runner.run_checks(AT_PARTNER, adapters=[BrokenAdapter(), ViesAdapter()])
    by_check = {r.check: r for r in results}
    assert by_check["brokenCheck"].result == "UNKNOWN"
    assert by_check["brokenCheck"].reason == "SOURCE_UNAVAILABLE"
    assert by_check["vatValid"].result == "TRUE"
    assert by_check["nameMatchesVat"].result == "TRUE"


def test_req_func_038_source_that_does_not_apply_is_not_applicable():
    results = runner.run_checks(DE_PARTNER, adapters=[AustriaOnlyAdapter()])
    assert results[0].result == "NOT_APPLICABLE"
    assert "dataTimestamp" not in results[0].to_json()


def test_req_maint_003_vies_is_registered():
    from checks.sources import ADAPTERS

    assert [type(a) for a in ADAPTERS] == [ViesAdapter]


# --- Added in the SRS review ---


def test_req_func_031_vies_error_in_4xx_body_keeps_the_vies_code():
    answer = vies_response(status=400, actionSucceed=False, errorWrappers=[{"error": "INVALID_INPUT"}])
    results, post = run_vies(AT_PARTNER, answer)
    assert post.call_count == 1  # 4xx is not transient (REQ-REL-003)
    assert results["vatValid"].reason == "SOURCE_UNAVAILABLE"
    assert results["vatValid"].details == {"error": "INVALID_INPUT"}


def test_req_func_031_is_valid_field_name_is_accepted():
    results, _ = run_vies(AT_PARTNER, vies_response(isValid=True, name="MUSTER BAU GMBH"))
    assert results["vatValid"].result == "TRUE"


def test_srs_3_2_4_data_timestamp_is_time_of_the_answering_query():
    times = iter(["first", "second"])
    with mock.patch("checks.sources.vies.utc_now", side_effect=lambda: next(times)):
        results, _ = run_vies(AT_PARTNER, requests.ConnectionError(), valid_answer())
    assert results["vatValid"].data_timestamp == "second"
