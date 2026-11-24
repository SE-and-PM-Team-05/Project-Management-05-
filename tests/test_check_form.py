"""SCRUM-85: the web form for a check (UC-05). VIES and HFU are always mocked; no test calls a real source."""

from unittest import mock

import pytest
from django.urls import reverse

from checks.models import CheckRequest
from tests.test_checks_api import URL, VALID_INPUT, make_user, vies_answer

FORM_URL = reverse("check_form")


@pytest.fixture
def vies():
    with mock.patch("checks.sources.http.requests.post", return_value=vies_answer()) as post:
        yield post


@pytest.fixture(autouse=True)
def hfu():
    with mock.patch("checks.sources.hfu.query_hfu", return_value={"dienstgeber": False, "epu": False}) as query:
        yield query


def comparable(checks):
    """The parts of each check result that don't depend on when it ran."""
    return [{k: v for k, v in check.items() if k != "dataTimestamp"} for check in checks]


def login(client, **roles):
    client.force_login(make_user(**roles))
    return client


def test_get_shows_the_form(client, db):
    """REQ-FUNC-042: a Request User gets the form, and the menu links to it."""
    page = login(client, is_request_user=True).get(FORM_URL).content.decode()
    assert 'name="vatNumber"' in page
    assert f'href="{FORM_URL}"' in page


def test_form_and_api_give_the_same_result(client, db, vies):
    """REQ-FUNC-042: the same input through the form and the API gives identical results."""
    login(client, is_request_user=True)
    api_body = client.post(URL, VALID_INPUT, content_type="application/json").json()
    response = client.post(FORM_URL, VALID_INPUT)
    assert response.status_code == 200
    assert "Partner check ATU12345678" in response.content.decode()  # the result page (REQ-FUNC-046)
    api_request, web_request = CheckRequest.objects.order_by("received_at")
    assert comparable(web_request.to_json()["checks"]) == comparable(api_body["checks"])
    assert web_request.to_json()["partner"] == api_body["partner"]


def test_form_check_is_stored_as_web(client, db, vies):
    """REQ-FUNC-050: a form check is stored with channel "web" and no token name."""
    login(client, is_request_user=True).post(FORM_URL, {**VALID_INPUT, "reference": "PO-4711"})
    stored = CheckRequest.objects.get()
    assert (stored.channel, stored.token_name, stored.reference) == ("web", "", "PO-4711")


def test_license_codes_are_split_at_commas(client, db, vies):
    """REQ-FUNC-030: comma-separated license codes in the form become the API's list."""
    login(client, is_request_user=True).post(FORM_URL, {**VALID_INPUT, "requiredLicenseCodes": " A1, ,B2 "})
    assert CheckRequest.objects.get().required_license_codes == ["A1", "B2"]


def test_invalid_input_shows_the_error_and_runs_nothing(client, db, vies):
    """REQ-FUNC-030: invalid input is shown on the form with the entered values; nothing is run or stored."""
    response = login(client, is_request_user=True).post(FORM_URL, {**VALID_INPUT, "vatNumber": "ATU1"})
    page = response.content.decode()
    assert response.status_code == 200
    assert 'name="vatNumber"' in page and 'value="ATU1"' in page
    assert "Nothing was checked" in page
    assert not vies.called
    assert not CheckRequest.objects.exists()


def test_anonymous_user_is_sent_to_login(client, db):
    """REQ-FUNC-012: the form needs a logged-in user."""
    assert client.get(FORM_URL).status_code == 302


def test_user_without_request_role_gets_403(client, db, vies):
    """REQ-FUNC-012: only Request Users may start a check, also through the form."""
    client = login(client, is_review_user=True)
    assert client.get(FORM_URL).status_code == 403
    assert client.post(FORM_URL, VALID_INPUT).status_code == 403
    assert not CheckRequest.objects.exists()
