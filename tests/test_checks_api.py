"""SCRUM-24: POST /api/v1/checks. VIES is always mocked; no test calls the real service."""

import re
from unittest import mock

import pytest
import requests
from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, User
from checks.models import CheckRequest, CheckRequestResult

URL = "/api/v1/checks"
VALID_INPUT = {"vatNumber": "atu 123.456-78", "companyName": "Muster Bau GmbH"}
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
    with mock.patch("checks.sources.vies.requests.post", return_value=vies_answer()) as post:
        yield post


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
    assert reverse("api_create_check") == URL


# --- Positive (REQ-FUNC-030, 031, 032, 045, 048) ---


def test_req_func_045_response_has_appendix_b_shape(api, vies):
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
    assert [c["check"] for c in body["checks"]] == ["vatValid", "nameMatchesVat"]


def test_req_func_031_032_valid_vat_and_matching_name(api, vies):
    checks = checks_of(post(api, VALID_INPUT))
    assert checks["vatValid"]["result"] == "TRUE"
    assert checks["vatValid"]["source"] == "VIES"
    assert ISO_UTC.match(checks["vatValid"]["dataTimestamp"])
    assert checks["vatValid"]["details"] == {"registeredAddress": "HAUPTSTRASSE 1, 3500 KREMS"}
    assert checks["nameMatchesVat"]["result"] == "TRUE"
    assert checks["nameMatchesVat"]["details"] == {"registeredName": "MUSTER BAU GMBH"}
    assert "reason" not in checks["vatValid"]


def test_req_func_030_vat_number_is_normalized_before_vies(api, vies):
    post(api, VALID_INPUT)
    assert vies.call_args.kwargs["json"] == {"countryCode": "AT", "vatNumber": "U12345678"}


def test_req_func_031_invalid_vat_returns_false(api, vies):
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
    vies.return_value = vies_answer(name="GANZ ANDERE GMBH")
    assert checks_of(post(api, VALID_INPUT))["nameMatchesVat"]["result"] == "FALSE"


# --- Source failure (REQ-INT-012, REQ-REL-001) ---


def test_req_int_012_vies_outage_still_returns_200_with_unknown(api, vies):
    vies.side_effect = requests.ConnectionError()
    response = post(api, VALID_INPUT)
    assert response.status_code == 200
    for check in checks_of(response).values():
        assert check["result"] == "UNKNOWN"
        assert check["reason"] == "SOURCE_UNAVAILABLE"
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
    response = post(api, data)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_INPUT"
    assert error["message"]
    assert set(error["fields"]) == fields
    vies.assert_not_called()


@pytest.mark.parametrize("body", ["not json", "[1, 2]", ""])
def test_req_int_012_body_that_is_not_a_json_object_returns_400(api, vies, body):
    response = api.post(URL, body, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] in ("INVALID_JSON", "INVALID_INPUT")
    vies.assert_not_called()


def test_req_func_031_other_eu_number_is_accepted(api, vies):
    assert post(api, {"vatNumber": "EL123456789", "companyName": "Ellas AE"}).status_code == 200
    assert vies.call_args.kwargs["json"] == {"countryCode": "EL", "vatNumber": "123456789"}


# --- Authentication and permissions (REQ-INT-011, REQ-FUNC-012) ---


def test_req_int_011_anonymous_call_returns_401(client, vies, db):
    response = post(client, VALID_INPUT)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    vies.assert_not_called()


@pytest.mark.django_db
def test_req_func_012_user_without_request_role_gets_403(client, vies):
    client.force_login(make_user(is_review_user=True, is_org_admin=True))
    response = post(client, VALID_INPUT)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    vies.assert_not_called()


@pytest.mark.django_db
def test_req_func_012_super_admin_cannot_start_a_check(client, vies):
    admin = User.objects.create_superuser("root@example.com", "x")
    client.force_login(admin)
    assert post(client, VALID_INPUT).status_code == 403


def test_req_func_013_response_names_only_the_own_organization(client, vies, db):
    make_user(email="other@example.com", org_name="Fremd Bau GmbH", is_request_user=True)
    user_b = User.objects.get(email="other@example.com")
    client.force_login(user_b)
    assert post(client, VALID_INPUT).json()["organization"] == "Fremd Bau GmbH"


def test_sec_session_post_without_csrf_token_is_rejected(request_user, vies):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(request_user)
    response = post(client, VALID_INPUT)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"
    vies.assert_not_called()


def test_req_int_012_get_returns_405_json(api):
    response = api.get(URL)
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


# --- Storing (REQ-REL-004, REQ-FUNC-041, REQ-FUNC-050, REQ-FUNC-051) ---


def test_req_rel_004_check_is_stored_with_all_results(api, vies, request_user):
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
    ]
    # The response is exactly what was stored.
    assert {**stored.to_json(), "disclaimer": body["disclaimer"]} == body


def test_req_func_050_request_with_unknown_results_is_stored_too(api, vies):
    vies.side_effect = requests.ConnectionError()
    body = post(api, VALID_INPUT).json()
    result = CheckRequestResult.objects.get(request_id=body["requestId"], check_name="vatValid")
    assert (result.result, result.reason, result.details) == (
        "UNKNOWN",
        "SOURCE_UNAVAILABLE",
        {"error": "NETWORK_ERROR"},
    )


def test_req_func_041_each_check_creates_a_new_record(api, vies):
    first = post(api, VALID_INPUT).json()["requestId"]
    second = post(api, VALID_INPUT).json()["requestId"]
    assert first != second
    assert CheckRequest.objects.count() == 2
    assert CheckRequestResult.objects.count() == 4


@pytest.mark.parametrize("data", [{}, {"vatNumber": "ATU1", "companyName": "X"}])
def test_req_func_030_invalid_input_stores_nothing(api, vies, data):
    assert post(api, data).status_code == 400
    assert not CheckRequest.objects.exists()


def test_req_int_011_rejected_calls_store_nothing(client, vies, db):
    assert post(client, VALID_INPUT).status_code == 401
    client.force_login(make_user(is_review_user=True))
    assert post(client, VALID_INPUT).status_code == 403
    assert not CheckRequest.objects.exists()


def test_req_rel_004_database_failure_returns_500_and_leaves_no_partial_record(api, vies):
    with mock.patch.object(CheckRequestResult.objects, "bulk_create", side_effect=DatabaseError("disk full")):
        response = post(api, VALID_INPUT)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert not CheckRequest.objects.exists()
    assert not CheckRequestResult.objects.exists()


def test_req_func_051_stored_results_cannot_be_changed(api, vies):
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
    post(api, VALID_INPUT)
    CheckRequest.objects.get().delete()
    assert not CheckRequestResult.objects.exists()


def test_req_comp_002_deleting_the_user_keeps_the_request_and_the_name(api, vies, request_user):
    post(api, VALID_INPUT)
    request_user.delete()
    stored = CheckRequest.objects.get()
    assert stored.requested_by is None
    assert stored.requested_by_name == "Anna Beispiel"


def test_req_func_013_request_is_stored_under_the_own_organization_only(client, vies, db):
    user_a = make_user(email="a@example.com", org_name="A Bau GmbH", is_request_user=True)
    user_b = make_user(email="b@example.com", org_name="B Bau GmbH", is_request_user=True)
    client.force_login(user_b)
    post(client, VALID_INPUT)
    assert not user_a.organization.check_requests.exists()
    assert user_b.organization.check_requests.count() == 1


# --- Added in the SRS review ---


def test_sec_session_post_with_csrf_token_is_accepted(request_user, vies):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(request_user)
    client.get(reverse("login"))  # sets the csrftoken cookie
    token = client.cookies["csrftoken"].value
    response = client.post(URL, VALID_INPUT, content_type="application/json", headers={"X-CSRFToken": token})
    assert response.status_code == 200


def test_req_int_012_unexpected_error_returns_500_json(api, vies):
    with mock.patch("checks.views.run_checks", side_effect=RuntimeError("bug")):
        response = post(api, VALID_INPUT)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
