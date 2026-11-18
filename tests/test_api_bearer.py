"""SCRUM-71: Bearer-token authentication for the API.

REQ-INT-011 (Bearer token or web session, else 401), REQ-FUNC-020 (expired token is 401), REQ-FUNC-021 (a token has
exactly its owner's rights at the time of use), REQ-FUNC-023 (revoked token or token of a deactivated user is 401
within 60 s), REQ-FUNC-045/050 (token name, never its value, in the response and the stored request), REQ-FUNC-013.
VIES is always mocked.
"""

import json
from datetime import timedelta
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ApiToken, Organization, User
from checks.models import CheckRequest

CHECKS_URL = "/api/v1/checks"
TOKENS_URL = "/api/v1/tokens"
VALID_INPUT = {"vatNumber": "ATU12345678", "companyName": "Muster Bau GmbH"}


def vies_answer():
    response = mock.Mock(status_code=200)
    response.json.return_value = {
        "countryCode": "AT",
        "vatNumber": "U12345678",
        "requestDate": "2026-11-16T09:00:00.000Z",
        "valid": True,
        "requestIdentifier": "",
        "name": "MUSTER BAU GMBH",
        "address": "HAUPTSTRASSE 1, 3500 KREMS",
    }
    return response


@pytest.fixture
def vies():
    with mock.patch("checks.sources.http.requests.post", return_value=vies_answer()) as post:
    with mock.patch("checks.sources.vies.requests.post", return_value=vies_answer()) as post:
        yield post


@pytest.fixture(autouse=True)
def hfu():
    """The HFU service is never called for real either; the partner is not on the list."""
    with mock.patch("checks.sources.hfu.query_hfu", return_value={"dienstgeber": False, "epu": False}) as query:
        yield query


def make_org(name="Beispiel Bau GmbH"):
    return Organization.objects.create(
        name=name, address="Hauptstraße 1, 3500 Krems", vat_number="ATU99999999", terms_accepted_at=timezone.now()
    )


def make_user(email, organization, **roles):
    return User.objects.create_user(
        email=email, password="x", first_name="Anna", last_name="Beispiel", organization=organization, **roles
    )


@pytest.fixture
def org(db):
    return make_org()


@pytest.fixture
def anna(org):
    return make_user("anna@beispielbau.at", org, is_request_user=True)


@pytest.fixture
def admin(org):
    return make_user("admin@beispielbau.at", org, is_org_admin=True)


@pytest.fixture
def reviewer(org):
    return make_user("ben@beispielbau.at", org, is_review_user=True)


@pytest.fixture
def anna_token(anna):
    """(token, full value) of a token owned by the Request User Anna."""
    return ApiToken.issue(anna, "ERP prod", created_by=anna)


@pytest.fixture
def api():
    """A client like a server-side program: CSRF is enforced, and it has no session."""
    return Client(enforce_csrf_checks=True)


def bearer(value):
    return {"Authorization": f"Bearer {value}"}


def start_check(client, value, data=VALID_INPUT):
    return client.post(CHECKS_URL, json.dumps(data), content_type="application/json", headers=bearer(value))


def assert_invalid_token(response):
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
    assert response["WWW-Authenticate"] == 'Bearer error="invalid_token"'


# --- A valid token works (REQ-INT-011, REQ-FUNC-020, REQ-FUNC-021) ----------------------------------------------


def test_valid_token_starts_a_check_without_session_or_csrf(api, vies, anna, anna_token):
    token, value = anna_token

    response = start_check(api, value)

    assert response.status_code == 200
    body = response.json()
    assert body["requestedBy"] == {"user": "Anna Beispiel", "channel": "api", "tokenName": "ERP prod"}
    assert body["organization"] == "Beispiel Bau GmbH"
    vies.assert_called_once()


def test_stored_request_names_the_token_but_never_its_value(api, vies, anna, anna_token):
    token, value = anna_token

    body = start_check(api, value).content.decode()

    stored = CheckRequest.objects.get()
    assert stored.requested_by == anna
    assert stored.channel == "api"
    assert stored.token_name == "ERP prod"
    assert value not in body
    assert value not in json.dumps(list(CheckRequest.objects.values()), default=str)


def test_scheme_is_case_insensitive(api, vies, anna_token):
    _, value = anna_token
    response = api.post(
        CHECKS_URL,
        json.dumps(VALID_INPUT),
        content_type="application/json",
        headers={"Authorization": f"bearer {value}"},
    )
    assert response.status_code == 200


def test_use_sets_last_used_date(api, vies, anna_token):
    token, value = anna_token
    assert token.last_used_at is None

    start_check(api, value)

    token.refresh_from_db()
    assert token.last_used_at is not None
    assert timezone.now() - token.last_used_at < timedelta(seconds=10)


def test_session_calls_still_work_without_a_token(client, vies, anna):
    # The web session stays a valid way in (REQ-INT-011); the existing session tests cover CSRF.
    client.force_login(anna)
    response = client.post(CHECKS_URL, json.dumps(VALID_INPUT), content_type="application/json")
    assert response.status_code == 200
    assert response.json()["requestedBy"]["tokenName"] is None


# --- Missing, unknown or malformed tokens (REQ-INT-011) ---------------------------------------------------------


def test_call_without_token_or_session_is_401(api, vies, db):
    response = api.post(CHECKS_URL, json.dumps(VALID_INPUT), content_type="application/json")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    vies.assert_not_called()


def test_unknown_token_is_401_and_stores_nothing(api, vies, anna_token):
    _, value = anna_token

    assert_invalid_token(start_check(api, value[:-1] + ("A" if value[-1] != "A" else "B")))

    vies.assert_not_called()
    assert not CheckRequest.objects.exists()


@pytest.mark.parametrize("header", ["Bearer", "Bearer ", "Basic YW5uYTp4", "Token abc", "Bearer a b", "abc"])
def test_malformed_authorization_header_is_401(api, vies, db, header):
    response = api.post(
        CHECKS_URL, json.dumps(VALID_INPUT), content_type="application/json", headers={"Authorization": header}
    )
    assert_invalid_token(response)
    vies.assert_not_called()


def test_bad_token_is_401_even_with_a_valid_session(client, vies, anna):
    # The Authorization header decides alone, so a broken integration is not hidden by someone's login.
    client.force_login(anna)
    assert_invalid_token(start_check(client, "not-a-token"))


def test_token_does_not_log_into_the_web_pages(api, anna_token):
    _, value = anna_token
    response = api.get(reverse("api_tokens"), headers=bearer(value))
    assert response.status_code == 302
    assert reverse("oidc_authentication_init") in response["Location"]


def test_value_shown_in_list_is_not_enough_to_authenticate(api, vies, anna_token):
    token, _ = anna_token
    assert_invalid_token(start_check(api, token.prefix))


def test_hash_of_the_value_is_not_accepted_as_token(api, vies, anna_token):
    token, _ = anna_token
    assert_invalid_token(start_check(api, token.token_hash))


# --- Revoked, expired, deactivated (REQ-FUNC-020, REQ-FUNC-023) -------------------------------------------------


def test_revoked_token_is_rejected_on_the_next_call(client, api, vies, anna, anna_token):
    token, value = anna_token
    assert start_check(api, value).status_code == 200

    client.force_login(anna)
    client.post(reverse("revoke_api_token", args=[token.pk]))

    assert_invalid_token(start_check(api, value))
    assert CheckRequest.objects.count() == 1


def test_expired_token_is_401(api, vies, anna):
    _, value = ApiToken.issue(anna, "old", created_by=anna, expires_at=timezone.now() - timedelta(seconds=1))
    assert_invalid_token(start_check(api, value))


def test_token_with_future_expiry_works(api, vies, anna):
    _, value = ApiToken.issue(anna, "temp", created_by=anna, expires_at=timezone.now() + timedelta(days=1))
    assert start_check(api, value).status_code == 200


def test_token_of_deactivated_user_is_401_and_stays_401_after_reactivation(client, api, vies, admin, anna, anna_token):
    _, value = anna_token
    client.force_login(admin)

    client.post(reverse("deactivate_member", args=[anna.pk]))
    assert_invalid_token(start_check(api, value))

    client.post(reverse("reactivate_member", args=[anna.pk]))
    assert_invalid_token(start_check(api, value))


def test_token_of_deactivated_user_is_401_even_if_not_revoked(api, vies, anna, anna_token):
    # QuerySet.update() skips User.save(), so the token is not revoked; the owner check still rejects it.
    _, value = anna_token
    User.objects.filter(pk=anna.pk).update(is_active=False)
    assert_invalid_token(start_check(api, value))


def test_token_of_deleted_user_is_401(api, vies, anna, anna_token):
    _, value = anna_token
    anna.delete()
    assert_invalid_token(start_check(api, value))


# --- Owner's rights at the time of use (REQ-FUNC-021) -----------------------------------------------------------


def test_review_only_users_token_cannot_start_a_check(api, vies, reviewer):
    _, value = ApiToken.issue(reviewer, "Reporting", created_by=reviewer)

    response = start_check(api, value)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    vies.assert_not_called()


def test_removing_the_role_takes_effect_on_the_next_call(api, vies, anna, anna_token):
    _, value = anna_token
    assert start_check(api, value).status_code == 200

    anna.is_request_user = False
    anna.save()

    assert start_check(api, value).status_code == 403


def test_org_admin_token_created_for_a_user_has_the_users_rights_not_the_admins(api, vies, admin, reviewer):
    _, value = ApiToken.issue(reviewer, "for Ben", created_by=admin)
    assert start_check(api, value).status_code == 403


# --- Token endpoints with a Bearer token ------------------------------------------------------------------------


def test_token_lists_only_its_owners_tokens(api, anna_token, reviewer):
    _, value = anna_token
    ApiToken.issue(reviewer, "Ben's", created_by=reviewer)

    response = api.get(TOKENS_URL, headers=bearer(value))

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["tokens"]] == ["ERP prod"]
    assert value not in response.content.decode()


def test_org_admin_token_lists_own_organization_only(api, admin, anna_token):
    _, value = ApiToken.issue(admin, "Admin", created_by=admin)
    other = make_user("eve@andere.at", make_org("Andere Bau GmbH"), is_org_admin=True)
    ApiToken.issue(other, "Eve's", created_by=other)

    names = {t["name"] for t in api.get(TOKENS_URL, headers=bearer(value)).json()["tokens"]}

    assert names == {"Admin", "ERP prod"}


def test_token_can_revoke_itself_without_csrf(api, vies, anna_token):
    token, value = anna_token

    assert api.delete(f"{TOKENS_URL}/{token.pk}", headers=bearer(value)).status_code == 204

    token.refresh_from_db()
    assert token.revoked_at is not None
    assert_invalid_token(start_check(api, value))


def test_token_of_other_organization_cannot_be_revoked_with_a_token(api, anna_token):
    _, value = anna_token
    other = make_user("eve@andere.at", make_org("Andere Bau GmbH"), is_request_user=True)
    other_token, _ = ApiToken.issue(other, "Eve's", created_by=other)

    assert api.delete(f"{TOKENS_URL}/{other_token.pk}", headers=bearer(value)).status_code == 404
    other_token.refresh_from_db()
    assert other_token.revoked_at is None


def test_token_cannot_create_new_tokens(api, admin):
    # A leaked token must not be able to mint replacements that survive its revocation (UN-04).
    _, value = ApiToken.issue(admin, "Admin", created_by=admin)

    response = api.post(
        TOKENS_URL, json.dumps({"name": "spare"}), content_type="application/json", headers=bearer(value)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert ApiToken.objects.count() == 1


# --- Robustness (REQ-INT-012) -----------------------------------------------------------------------------------


def test_error_during_token_lookup_returns_json_500(api, vies, anna_token):
    _, value = anna_token
    with mock.patch("accounts.middleware.authenticate_token", side_effect=RuntimeError("db down")):
        response = start_check(api, value)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    vies.assert_not_called()


def test_health_check_ignores_authorization_header(api, db):
    assert api.get(reverse("healthz"), headers=bearer("whatever")).content == b"ok"
