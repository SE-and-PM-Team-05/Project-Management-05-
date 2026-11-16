"""SCRUM-73: at most 200 API requests per minute per token (REQ-SEC-003, UC-04 alternative flow 2b).

The 201st request within a minute gets 429 with Retry-After; the remaining quota is in the X-RateLimit-* headers;
a rejected check is not run and not stored. VIES is always mocked.
"""

import json
from datetime import timedelta
from unittest import mock

import pytest
from django.test import Client
from django.utils import timezone

from accounts.api_auth import RATE_LIMIT
from accounts.models import ApiToken, Organization, User
from checks.models import CheckRequest

CHECKS_URL = "/api/v1/checks"
TOKENS_URL = "/api/v1/tokens"
VALID_INPUT = {"vatNumber": "ATU12345678", "companyName": "Muster Bau GmbH"}


@pytest.fixture
def vies():
    answer = mock.Mock(status_code=200)
    answer.json.return_value = {
        "countryCode": "AT",
        "vatNumber": "U12345678",
        "requestDate": "2026-11-16T09:00:00.000Z",
        "valid": True,
        "requestIdentifier": "",
        "name": "MUSTER BAU GMBH",
        "address": "HAUPTSTRASSE 1, 3500 KREMS",
    }
    with mock.patch("checks.sources.vies.requests.post", return_value=answer) as post:
        yield post


@pytest.fixture
def anna(db):
    org = Organization.objects.create(
        name="Beispiel Bau GmbH", address="Hauptstraße 1", vat_number="ATU99999999", terms_accepted_at=timezone.now()
    )
    return User.objects.create_user(email="anna@beispielbau.at", password="x", organization=org, is_request_user=True)


@pytest.fixture
def anna_token(anna):
    return ApiToken.issue(anna, "ERP prod", created_by=anna)


@pytest.fixture
def api():
    return Client(enforce_csrf_checks=True)


def bearer(value):
    return {"Authorization": f"Bearer {value}"}


def list_tokens(client, value):
    """The cheapest authenticated call; it counts against the limit like any other."""
    return client.get(TOKENS_URL, headers=bearer(value))


def start_check(client, value):
    return client.post(CHECKS_URL, json.dumps(VALID_INPUT), content_type="application/json", headers=bearer(value))


def use_up(token, seconds_ago=0):
    """Put the token at its limit in a window that started `seconds_ago` seconds ago."""
    ApiToken.objects.filter(pk=token.pk).update(
        rate_window_started_at=timezone.now() - timedelta(seconds=seconds_ago), rate_window_count=RATE_LIMIT
    )


def test_limit_is_200_per_minute():
    assert RATE_LIMIT == 200


def test_201st_request_within_a_minute_gets_429_with_retry_after(api, anna_token):
    _, value = anna_token

    for i in range(RATE_LIMIT):
        response = list_tokens(api, value)
        assert response.status_code == 200, f"request {i + 1}"
        assert response["X-RateLimit-Remaining"] == str(RATE_LIMIT - i - 1)

    response = list_tokens(api, value)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert 1 <= int(response["Retry-After"]) <= 60
    assert response["X-RateLimit-Limit"] == "200"
    assert response["X-RateLimit-Remaining"] == "0"


def test_quota_headers_on_every_token_call(api, vies, anna_token):
    _, value = anna_token

    response = start_check(api, value)

    assert response.status_code == 200
    assert response["X-RateLimit-Limit"] == "200"
    assert response["X-RateLimit-Remaining"] == "199"
    assert 1 <= int(response["X-RateLimit-Reset"]) <= 60
    assert "Retry-After" not in response


def test_rejected_check_is_not_run_and_not_stored(api, vies, anna_token):
    token, value = anna_token
    use_up(token)

    response = start_check(api, value)

    assert response.status_code == 429
    vies.assert_not_called()
    assert not CheckRequest.objects.exists()


def test_retry_after_counts_down_to_the_end_of_the_window(api, anna_token):
    token, value = anna_token
    use_up(token, seconds_ago=50)

    response = list_tokens(api, value)

    assert response.status_code == 429
    assert 8 <= int(response["Retry-After"]) <= 10
    assert response["Retry-After"] == response["X-RateLimit-Reset"]


def test_new_window_starts_after_a_minute(api, anna_token):
    token, value = anna_token
    use_up(token, seconds_ago=61)

    response = list_tokens(api, value)

    assert response.status_code == 200
    assert response["X-RateLimit-Remaining"] == "199"


def test_rejected_calls_are_not_counted_and_do_not_change_last_use(api, anna_token):
    token, value = anna_token
    use_up(token)
    token.refresh_from_db()

    for _ in range(3):
        assert list_tokens(api, value).status_code == 429

    after = ApiToken.objects.get(pk=token.pk)
    assert after.rate_window_count == RATE_LIMIT
    assert after.rate_window_started_at == token.rate_window_started_at
    assert after.last_used_at == token.last_used_at


def test_limit_is_per_token(api, vies, anna, anna_token):
    token, value = anna_token
    use_up(token)
    _, other_value = ApiToken.issue(anna, "Second system", created_by=anna)

    assert start_check(api, value).status_code == 429
    response = start_check(api, other_value)
    assert response.status_code == 200
    assert response["X-RateLimit-Remaining"] == "199"


def test_invalid_token_is_401_not_429(api, anna_token):
    token, value = anna_token
    use_up(token)
    token.revoke()

    response = list_tokens(api, value)

    assert response.status_code == 401
    assert "X-RateLimit-Remaining" not in response


def test_web_session_calls_are_not_limited_per_token(client, vies, anna):
    client.force_login(anna)

    response = client.post(CHECKS_URL, json.dumps(VALID_INPUT), content_type="application/json")

    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response
