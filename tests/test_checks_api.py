"""SCRUM-24: POST /api/v1/checks. VIES is always mocked; no test calls the real service."""

import re
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
import requests
from django.contrib import admin
from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from accounts.models import Organization, User
from checks.models import CheckRequest, CheckRequestResult
from checks.sources.base import SourceAdapter
from checks.sources.vies import ViesAdapter
from checks.views import DISCLAIMER

URL = "/api/v1/checks"
VALID_INPUT = {"vatNumber": "atu 123.456-78", "companyName": "Muster Bau GmbH"}
# The request user's organization (make_user) is sent to VIES as requester (REQ-FUNC-050).
REQUESTER = {"requesterMemberStateCode": "AT", "requesterNumber": "U99999999"}
ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def vies_answer(valid=True, name="MUSTER BAU GMBH"):
    response = mock.Mock(status_code=200)
    response.json.return_value = {
        "countryCode": "AT",
        "vatNumber": "U12345678",
        "requestDate": "2026-11-02T09:00:00.000Z",
        "valid": valid,
        "requestIdentifier": "",
        "name": name,
        "address": "HAUPTSTRASSE 1, 3500 KREMS",
    }
    return response


@pytest.fixture
def vies():
    with mock.patch("checks.sources.http.requests.post", return_value=vies_answer()) as post:
        yield post


@pytest.fixture(autouse=True)
def hfu():
    with mock.patch(
        "checks.sources.hfu.query_hfu",
        return_value={"dienstgeber": False, "epu": False},
    ) as query:
        yield query


def make_user(email="anna@beispielbau.at", org_name="Beispiel Bau GmbH", **roles):
    org = Organization.objects.create(
        name=org_name, address="Hauptstraße 1", vat_number="ATU99999999", is_verified=True,
        terms_accepted_at=timezone.now(),
    )  # fmt: skip
    return User.objects.create_user(
        email=email, password="x", first_name="Anna", last_name="Beispiel", organization=org, **roles
    )


@pytest.fixture
def request_user(db):
    return make_user(is_request_user=True)


@pytest.fixture
def api(client, request_user):
    client.force_login(request_user)
    return client


def post(client, data):
    return client.post(URL, data, content_type="application/json")


def checks_of(response):
    return {c["check"]: c for c in response.json()["checks"]}


def test_req_int_010_route_is_versioned():
    """Verifies REQ-INT-010."""
    assert reverse("api_create_check") == URL


# --- Positive (REQ-FUNC-030, 031, 032, 045, 048) ---


def test_req_func_045_response_has_appendix_b_shape(api, vies):
    """Verifies REQ-FUNC-045."""
    response = post(api, {**VALID_INPUT, "companyRegisterNumber": "FN 123456a", "reference": "PO-4711"})
    assert response.status_code == 200
    body = response.json()
    assert re.fullmatch(r"[0-9a-f-]{36}", body["requestId"])
    assert ISO_UTC.match(body["receivedAt"]) and ISO_UTC.match(body["completedAt"])
    assert body["organization"] == "Beispiel Bau GmbH"
    assert body["requestedBy"] == {"user": "Anna Beispiel", "channel": "api", "tokenName": None}
    assert body["partner"] == {
        "companyName": "Muster Bau GmbH",
        "vatNumber": "ATU12345678",
        "companyRegisterNumber": "123456a",
    }
    assert body["reference"] == "PO-4711"
    assert "no liability" in body["disclaimer"]  # REQ-FUNC-048
    # Only the checks implemented so far; nothing invented for the others.
    assert [c["check"] for c in body["checks"]] == [
        "vatValid",
        "nameMatchesVat",
        "listedAsFakeCompany",
        "onHfuList",
    ]


def test_req_func_031_032_valid_vat_and_matching_name(api, vies):
    """Verifies REQ-FUNC-031, REQ-FUNC-032."""
    checks = checks_of(post(api, VALID_INPUT))
    assert checks["vatValid"]["result"] == "TRUE"
    assert checks["vatValid"]["source"] == "VIES"
    assert ISO_UTC.match(checks["vatValid"]["dataTimestamp"])
    assert checks["vatValid"]["details"] == {"registeredAddress": "HAUPTSTRASSE 1, 3500 KREMS"}
    assert checks["nameMatchesVat"]["result"] == "TRUE"
    assert checks["nameMatchesVat"]["details"] == {"registeredName": "MUSTER BAU GMBH"}
    assert "reason" not in checks["vatValid"]


def test_req_func_030_vat_number_is_normalized_before_vies(api, vies):
    """Verifies REQ-FUNC-030."""
    post(api, VALID_INPUT)
    assert vies.call_args.kwargs["json"] == {"countryCode": "AT", "vatNumber": "U12345678", **REQUESTER}


def test_req_func_031_invalid_vat_returns_false(api, vies):
    """Verifies REQ-FUNC-031."""
    vies.return_value = vies_answer(valid=False, name="---")
    checks = checks_of(post(api, VALID_INPUT))
    assert checks["vatValid"]["result"] == "FALSE"
    assert checks["nameMatchesVat"] == {
        "check": "nameMatchesVat",
        "result": "UNKNOWN",
        "reason": "NO_DETAILS_FOUND",
        "source": "VIES",
        "dataTimestamp": checks["nameMatchesVat"]["dataTimestamp"],
    }


def test_req_func_032_other_company_returns_false(api, vies):
    """Verifies REQ-FUNC-032."""
    vies.return_value = vies_answer(name="GANZ ANDERE GMBH")
    assert checks_of(post(api, VALID_INPUT))["nameMatchesVat"]["result"] == "FALSE"


# --- Source failure (REQ-INT-012, REQ-REL-001) ---


def test_req_int_012_vies_outage_still_returns_200_with_unknown(api, vies):
    """Verifies REQ-INT-012."""
    vies.side_effect = requests.ConnectionError()
    response = post(api, VALID_INPUT)
    assert response.status_code == 200
    checks = checks_of(response)
    for name in ("vatValid", "nameMatchesVat"):
        assert checks[name]["result"] == "UNKNOWN"
        assert checks[name]["reason"] == "SOURCE_UNAVAILABLE"
    # Other sources are independent of VIES and still answer (REQ-FUNC-039).
    assert checks["onHfuList"]["result"] == "FALSE"
    assert "no liability" in response.json()["disclaimer"]


# --- Invalid input (REQ-FUNC-030, REQ-INT-012) ---


@pytest.mark.parametrize(
    ("data", "fields"),
    [
        ({}, {"vatNumber", "companyName"}),
        ({"companyName": "Muster Bau GmbH"}, {"vatNumber"}),
        ({"vatNumber": "ATU12345678"}, {"companyName"}),
        ({"vatNumber": "ATU12345678", "companyName": "   "}, {"companyName"}),
        ({"vatNumber": "ATU1234567", "companyName": "X"}, {"vatNumber"}),
        ({"vatNumber": "US123456789", "companyName": "X"}, {"vatNumber"}),
        ({"vatNumber": "GR123456789", "companyName": "X"}, {"vatNumber"}),  # Greece is EL in VIES
        ({"vatNumber": 12345678, "companyName": "X"}, {"vatNumber"}),
        ({**VALID_INPUT, "companyRegisterNumber": "12345"}, {"companyRegisterNumber"}),
        ({**VALID_INPUT, "requiredLicenseCodes": "abc"}, {"requiredLicenseCodes"}),
        ({**VALID_INPUT, "companyName": "x" * 201}, {"companyName"}),
    ],
)
def test_req_func_030_invalid_input_returns_400_without_calling_vies(api, vies, data, fields):
    """Verifies REQ-FUNC-030."""
    response = post(api, data)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_INPUT"
    assert error["message"]
    assert set(error["fields"]) == fields
    vies.assert_not_called()


@pytest.mark.parametrize("body", ["not json", "[1, 2]", ""])
def test_req_int_012_body_that_is_not_a_json_object_returns_400(api, vies, body):
    """Verifies REQ-INT-012."""
    response = api.post(URL, body, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] in ("INVALID_JSON", "INVALID_INPUT")
    vies.assert_not_called()


def test_req_func_031_other_eu_number_is_accepted(api, vies, hfu):
    """Verifies REQ-FUNC-031."""
    response = post(api, {"vatNumber": "EL123456789", "companyName": "Ellas AE"})
    assert response.status_code == 200
    assert vies.call_args.kwargs["json"] == {"countryCode": "EL", "vatNumber": "123456789", **REQUESTER}
    # HFU is asked by Austrian VAT number only (REQ-FUNC-038).
    assert checks_of(response)["onHfuList"]["result"] == "NOT_APPLICABLE"
    hfu.assert_not_called()


# --- Authentication and permissions (REQ-INT-011, REQ-FUNC-012) ---


def test_req_int_011_anonymous_call_returns_401(client, vies, db):
    """Verifies REQ-INT-011."""
    response = post(client, VALID_INPUT)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    vies.assert_not_called()


@pytest.mark.django_db
def test_req_func_012_user_without_request_role_gets_403(client, vies):
    """Verifies REQ-FUNC-012."""
    client.force_login(make_user(is_review_user=True, is_org_admin=True))
    response = post(client, VALID_INPUT)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    vies.assert_not_called()


@pytest.mark.django_db
def test_req_func_012_super_admin_cannot_start_a_check(client, vies):
    """Verifies REQ-FUNC-012."""
    admin = User.objects.create_superuser("root@example.com", "x")
    client.force_login(admin)
    assert post(client, VALID_INPUT).status_code == 403


def test_req_func_013_response_names_only_the_own_organization(client, vies, db):
    """Verifies REQ-FUNC-013."""
    make_user(email="other@example.com", org_name="Fremd Bau GmbH", is_request_user=True)
    user_b = User.objects.get(email="other@example.com")
    client.force_login(user_b)
    assert post(client, VALID_INPUT).json()["organization"] == "Fremd Bau GmbH"


def test_sec_session_post_without_csrf_token_is_rejected(request_user, vies):
    """Verifies REQ-SEC-006."""
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(request_user)
    response = post(client, VALID_INPUT)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"
    vies.assert_not_called()


def test_req_int_012_get_returns_405_json(api):
    """Verifies REQ-INT-012."""
    response = api.get(URL)
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


# --- Storing (REQ-REL-004, REQ-FUNC-041, REQ-FUNC-050, REQ-FUNC-051) ---


def test_req_rel_004_check_is_stored_with_all_results(api, vies, request_user):
    """Verifies REQ-REL-004."""
    body = post(api, {**VALID_INPUT, "companyRegisterNumber": "123456a", "reference": "PO-4711"}).json()

    stored = CheckRequest.objects.get()
    assert body["requestId"] == str(stored.id)
    assert stored.organization == request_user.organization
    assert stored.requested_by == request_user
    assert stored.requested_by_name == "Anna Beispiel"
    assert stored.channel == "api"
    assert stored.vat_number == "ATU12345678"
    assert stored.company_name == "Muster Bau GmbH"
    assert stored.company_register_number == "123456a"
    assert stored.reference == "PO-4711"
    assert stored.received_at <= stored.completed_at
    assert [(r.check_name, r.result) for r in stored.results.all()] == [
        ("vatValid", "TRUE"),
        ("nameMatchesVat", "TRUE"),
        ("listedAsFakeCompany", "UNKNOWN"),  # no list sync in this test
        ("onHfuList", "FALSE"),
    ]
    # The response is exactly what was stored.
    assert {**stored.to_json(), "disclaimer": body["disclaimer"]} == body


def test_req_func_050_request_with_unknown_results_is_stored_too(api, vies):
    """Verifies REQ-FUNC-050."""
    vies.side_effect = requests.ConnectionError()
    body = post(api, VALID_INPUT).json()
    result = CheckRequestResult.objects.get(request_id=body["requestId"], check_name="vatValid")
    assert (result.result, result.reason, result.details) == (
        "UNKNOWN",
        "SOURCE_UNAVAILABLE",
        {"error": "NETWORK_ERROR"},
    )


class FailingSource(SourceAdapter):
    source = "FAILING"
    checks = ("failingCheck",)

    def run(self, partner, deadline):
        raise ConnectionError("source is down")


def test_scrum_60_failing_source_still_returns_200_and_the_request_is_stored(api, vies):
    """REQ-FUNC-039, REQ-REL-001.

    One source stubbed to fail: the others answer, the response is 200 and everything is stored
    (REQ-FUNC-039, REQ-REL-001, REQ-INT-012)."""
    with mock.patch("checks.runner.ADAPTERS", [ViesAdapter(), FailingSource()]):
        response = post(api, VALID_INPUT)
    assert response.status_code == 200
    checks = checks_of(response)
    assert checks["vatValid"]["result"] == "TRUE"
    assert checks["nameMatchesVat"]["result"] == "TRUE"
    assert (checks["failingCheck"]["result"], checks["failingCheck"]["reason"]) == ("UNKNOWN", "SOURCE_UNAVAILABLE")
    stored = CheckRequest.objects.get(pk=response.json()["requestId"])
    assert [(r.check_name, r.result) for r in stored.results.all()] == [
        ("vatValid", "TRUE"),
        ("nameMatchesVat", "TRUE"),
        ("failingCheck", "UNKNOWN"),
    ]


# --- Evidence fields (SCRUM-61, REQ-FUNC-050) ---


def test_req_func_050_all_evidence_fields_are_stored_for_an_unknown_request(api, vies, request_user):
    """REQ-FUNC-050.

    The acceptance test of REQ-FUNC-050: every field is in the database, also when results are UNKNOWN.
    """
    vies.side_effect = requests.ConnectionError()
    data = {
        **VALID_INPUT,
        "companyRegisterNumber": "FN 123456a",
        "address": "Ringstraße 1, 3500 Krems",
        "requiredLicenseCodes": ["BAUMEISTER"],
        "reference": "PO-4711",
    }
    response = post(api, data)
    assert response.status_code == 200
    stored = CheckRequest.objects.get(pk=response.json()["requestId"])

    assert stored.organization == request_user.organization
    assert stored.requested_by == request_user
    assert stored.requested_by_name == "Anna Beispiel"
    assert stored.channel == CheckRequest.CHANNEL_API
    assert stored.token_name == ""  # web session; a Bearer call stores the token's name (SCRUM-71)
    assert (stored.vat_number, stored.company_name) == ("ATU12345678", "Muster Bau GmbH")
    assert stored.company_register_number == "123456a"
    assert stored.address == "Ringstraße 1, 3500 Krems"
    assert stored.required_license_codes == ["BAUMEISTER"]
    assert stored.reference == "PO-4711"
    assert stored.received_at <= stored.completed_at
    results = list(stored.results.all())
    assert [(r.check_name, r.result, r.reason, r.source) for r in results] == [
        ("vatValid", "UNKNOWN", "SOURCE_UNAVAILABLE", "VIES"),
        ("nameMatchesVat", "UNKNOWN", "SOURCE_UNAVAILABLE", "VIES"),
        ("listedAsFakeCompany", "UNKNOWN", "SOURCE_UNAVAILABLE", "BMF"),
        ("onHfuList", "FALSE", "", "OEGK"),
    ]
    assert all(r.data_timestamp for r in results)
    assert all(r.details == {"error": "NETWORK_ERROR"} for r in results if r.source == "VIES")


def test_req_func_050_vies_reference_number_is_stored(api, vies):
    """Verifies REQ-FUNC-050."""
    answer = vies_answer()
    answer.json.return_value["requestIdentifier"] = "WAPIAAAAZ1b2c3d4"
    vies.return_value = answer
    body = post(api, VALID_INPUT).json()
    stored = CheckRequestResult.objects.get(request_id=body["requestId"], check_name="vatValid")
    assert stored.details["requestIdentifier"] == "WAPIAAAAZ1b2c3d4"
    assert checks_of_body(body)["vatValid"]["details"]["requestIdentifier"] == "WAPIAAAAZ1b2c3d4"


def test_req_func_050_list_sync_time_is_stored_as_data_timestamp(api, vies):
    """REQ-FUNC-050: For a list source the result's dataTimestamp is the sync it is based on (SRS 3.2.4, Appendix B)."""
    synced_at = timezone.now() - timedelta(hours=6)

    class ListSource(SourceAdapter):
        source = "TEST_LIST"
        checks = ("onTestList",)

        def run(self, partner, deadline):
            return [self.result("onTestList", "FALSE", synced_at)]

    with mock.patch("checks.runner.ADAPTERS", [ViesAdapter(), ListSource()]):
        body = post(api, VALID_INPUT).json()
    stored = CheckRequestResult.objects.get(request_id=body["requestId"], check_name="onTestList")
    assert stored.data_timestamp == synced_at


# --- HTML result page (REQ-FUNC-046) ---


def text_values(value):
    """Every string and number in a JSON value, however deeply nested."""
    if isinstance(value, dict):
        return [v for item in value.values() for v in text_values(item)]
    if isinstance(value, list):
        return [v for item in value for v in text_values(item)]
    if isinstance(value, bool) or value is None:
        return []
    return [str(value)]


def test_req_func_046_html_page_shows_every_json_field(api, vies):
    """REQ-FUNC-046, REQ-FUNC-048: Accept: text/html gives a page with every value of the JSON body."""
    data = {**VALID_INPUT, "companyRegisterNumber": "123456a", "address": "Hauptstraße 1", "reference": "PO-4711"}
    response = api.post(URL, data, content_type="application/json", HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    page = response.content.decode()
    body = {**CheckRequest.objects.get().to_json(), "disclaimer": str(DISCLAIMER)}
    missing = [value for value in text_values(body) if escape(value) not in page]
    assert not missing
    assert "@media print" in page  # printable: the site header is hidden when printing


@pytest.mark.parametrize("accept", [None, "*/*", "application/json", "text/html;q=0.5, application/json"])
def test_req_func_046_json_stays_the_default(api, vies, accept):
    """REQ-FUNC-046: JSON unless the client prefers HTML."""
    headers = {"HTTP_ACCEPT": accept} if accept else {}
    response = api.post(URL, VALID_INPUT, content_type="application/json", **headers)
    assert response["Content-Type"] == "application/json"
    assert "requestId" in response.json()


def checks_of_body(body):
    return {c["check"]: c for c in body["checks"]}


def test_req_func_041_each_check_creates_a_new_record(api, vies):
    """Verifies REQ-FUNC-041."""
    first = post(api, VALID_INPUT).json()["requestId"]
    second = post(api, VALID_INPUT).json()["requestId"]
    assert first != second
    assert CheckRequest.objects.count() == 2
    assert CheckRequestResult.objects.count() == 8  # 4 checks per request: VIES (2), BMF, HFU


@pytest.mark.parametrize("data", [{}, {"vatNumber": "ATU1", "companyName": "X"}])
def test_req_func_030_invalid_input_stores_nothing(api, vies, data):
    """Verifies REQ-FUNC-030."""
    assert post(api, data).status_code == 400
    assert not CheckRequest.objects.exists()


def test_req_int_011_rejected_calls_store_nothing(client, vies, db):
    """Verifies REQ-INT-011."""
    assert post(client, VALID_INPUT).status_code == 401
    client.force_login(make_user(is_review_user=True))
    assert post(client, VALID_INPUT).status_code == 403
    assert not CheckRequest.objects.exists()


def test_req_rel_004_database_failure_returns_500_and_leaves_no_partial_record(api, vies):
    """Verifies REQ-REL-004."""
    with mock.patch.object(CheckRequestResult.objects, "bulk_create", side_effect=DatabaseError("disk full")):
        response = post(api, VALID_INPUT)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert not CheckRequest.objects.exists()
    assert not CheckRequestResult.objects.exists()


def test_req_func_051_stored_results_cannot_be_changed(api, vies):
    """Verifies REQ-FUNC-051."""
    post(api, VALID_INPUT)
    stored = CheckRequest.objects.get()
    stored.company_name = "Changed"
    with pytest.raises(ValueError):
        stored.save()
    result = stored.results.first()
    result.result = "FALSE"
    with pytest.raises(ValueError):
        result.save()
    stored.refresh_from_db()
    assert stored.company_name == "Muster Bau GmbH"
    assert stored.results.first().result == "TRUE"


def test_req_func_051_request_can_be_deleted_as_a_whole(api, vies):
    """Verifies REQ-FUNC-051."""
    post(api, VALID_INPUT)
    CheckRequest.objects.get().delete()
    assert not CheckRequestResult.objects.exists()


# --- Immutable results (SCRUM-62, REQ-FUNC-040, REQ-FUNC-041, REQ-FUNC-051) ---

REPO = Path(__file__).resolve().parent.parent


def test_req_func_051_queryset_update_and_bulk_update_are_blocked(api, vies):
    """REQ-FUNC-051: update() and bulk_update() skip save(), so the QuerySet blocks them as well."""
    post(api, VALID_INPUT)
    stored = CheckRequest.objects.get()
    with pytest.raises(ValueError):
        CheckRequest.objects.update(company_name="Changed")
    with pytest.raises(ValueError):
        stored.results.update(result="FALSE")
    with pytest.raises(ValueError):
        CheckRequestResult.objects.filter(request=stored).update(result="FALSE")
    results = list(stored.results.all())
    for result in results:
        result.result = "FALSE"
    with pytest.raises(ValueError):
        CheckRequestResult.objects.bulk_update(results, ["result"])
    stored.refresh_from_db()
    assert stored.company_name == "Muster Bau GmbH"
    assert [r.result for r in stored.results.all()] == [
        "TRUE",
        "TRUE",
        "UNKNOWN",
        "FALSE",
    ]  # vatValid, nameMatchesVat, listedAsFakeCompany (no sync), onHfuList


@pytest.mark.parametrize("model", [CheckRequest, CheckRequestResult])
def test_req_func_051_stored_results_are_not_editable_in_the_admin(model):
    """REQ-FUNC-051: Not even a super admin can edit evidence; a read-only admin would need its own review."""
    assert not admin.site.is_registered(model)


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_req_func_051_api_has_no_update_path(api, vies, method):
    """Verifies REQ-FUNC-051."""
    request_id = post(api, VALID_INPUT).json()["requestId"]
    response = getattr(api, method)(URL, {"companyName": "Changed"}, content_type="application/json")
    assert response.status_code == 405
    assert response["Allow"] == "POST"
    # There is no route for a single stored request yet, so nothing can address it either.
    response = getattr(api, method)(f"{URL}/{request_id}", {"companyName": "Changed"}, content_type="application/json")
    assert response.status_code == 404
    assert CheckRequest.objects.get().company_name == "Muster Bau GmbH"


def test_req_func_041_two_checks_of_the_same_partner_give_two_records_with_different_timestamps(api, vies):
    """REQ-FUNC-041: The acceptance test of REQ-FUNC-041: the second check does not overwrite the first."""
    start = timezone.now()
    times = iter([start, start + timedelta(seconds=1), start + timedelta(days=1), start + timedelta(days=1, seconds=1)])
    with mock.patch("checks.views.utc_now", side_effect=lambda: next(times)):
        first = post(api, VALID_INPUT).json()
        vies.return_value = vies_answer(valid=False)
        second = post(api, VALID_INPUT).json()

    assert first["requestId"] != second["requestId"]
    assert first["receivedAt"] != second["receivedAt"]
    older = CheckRequest.objects.get(pk=first["requestId"])
    newer = CheckRequest.objects.get(pk=second["requestId"])
    assert older.received_at < newer.received_at
    # The earlier result stays as it was, although the later check came to a different result.
    assert checks_of_body(older.to_json())["vatValid"]["result"] == "TRUE"
    assert checks_of_body(newer.to_json())["vatValid"]["result"] == "FALSE"


def test_req_func_040_advancing_time_creates_no_new_result(api, vies):
    """REQ-FUNC-040: Results are not recomputed or re-checked when they are read later, not even a year later."""
    request_id = post(api, VALID_INPUT).json()["requestId"]
    before = CheckRequest.objects.get().to_json()

    later = timezone.now() + timedelta(days=400)
    with (
        mock.patch("django.utils.timezone.now", return_value=later),
        mock.patch("checks.results.utc_now", return_value=later),
    ):
        after = CheckRequest.objects.get(pk=request_id).to_json()

    assert after == before
    assert CheckRequest.objects.count() == 1
    assert CheckRequestResult.objects.count() == 4  # VIES (2), BMF, HFU
    assert vies.call_count == 1


def python_files_outside_tests():
    """The project's own Python code: every top-level package, without tests and migrations."""
    for package in sorted(p.parent for p in REPO.glob("*/__init__.py")):
        if package.name == "tests":
            continue
        for path in package.rglob("*.py"):
            if "migrations" not in path.parts:
                yield path.relative_to(REPO).as_posix(), path.read_text(encoding="utf-8")


def test_req_func_040_only_a_user_or_client_request_runs_and_stores_checks():
    """REQ-FUNC-040: Code inspection as a test: a sync job, management command or signal must not re-check partners.

    Checks are run and stored only in the view that handles a user's or client system's request. A new caller
    (e.g. the web form, REQ-FUNC-042) must also be started by a user and is added here on purpose.
    """
    allowed = {"checks/views.py"}
    run = re.compile(r"\brun_checks\(")
    store = re.compile(
        r"(?<!class )\bCheckRequest(?:Result)?(?:\.objects\.(?:create|bulk_create|get_or_create|update_or_create)|\()"
    )
    callers = {name for name, text in python_files_outside_tests() if run.search(text) and name != "checks/runner.py"}
    writers = {name for name, text in python_files_outside_tests() if store.search(text)}
    assert callers <= allowed
    assert writers <= allowed
    assert "checks/views.py" in callers & writers  # the pattern still finds the real caller


def test_req_comp_002_deleting_the_user_keeps_the_request_and_the_name(api, vies, request_user):
    """Verifies REQ-COMP-002."""
    post(api, VALID_INPUT)
    request_user.delete()
    stored = CheckRequest.objects.get()
    assert stored.requested_by is None
    assert stored.requested_by_name == "Anna Beispiel"


def test_req_func_013_request_is_stored_under_the_own_organization_only(client, vies, db):
    """Verifies REQ-FUNC-013."""
    user_a = make_user(email="a@example.com", org_name="A Bau GmbH", is_request_user=True)
    user_b = make_user(email="b@example.com", org_name="B Bau GmbH", is_request_user=True)
    client.force_login(user_b)
    post(client, VALID_INPUT)
    assert not user_a.organization.check_requests.exists()
    assert user_b.organization.check_requests.count() == 1


# --- Added in the SRS review ---


def test_sec_session_post_with_csrf_token_is_accepted(request_user, vies):
    """Verifies REQ-SEC-006."""
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(request_user)
    client.get(reverse("home"))  # the logout form sets the csrftoken cookie
    token = client.cookies["csrftoken"].value
    response = client.post(URL, VALID_INPUT, content_type="application/json", headers={"X-CSRFToken": token})
    assert response.status_code == 200


def test_req_int_012_unexpected_error_returns_500_json(api, vies):
    """Verifies REQ-INT-012."""
    with mock.patch("checks.views.run_checks", side_effect=RuntimeError("bug")):
        response = post(api, VALID_INPUT)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_req_func_034_hfu_query_uses_requesting_organization_vat(api, hfu):
    """Verifies REQ-FUNC-034."""
    post(api, VALID_INPUT)

    assert hfu.call_args.kwargs["organization_uid"] == "ATU99999999"
    assert hfu.call_args.kwargs["partner_uid"] == "ATU12345678"
