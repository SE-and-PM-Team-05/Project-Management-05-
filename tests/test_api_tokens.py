"""SCRUM-72: create, list and revoke API tokens on the web page and through the API.

REQ-FUNC-020 (create, optional expiry), REQ-FUNC-022 (value shown once), REQ-FUNC-023 (list, revoke, deactivating or
deleting a user revokes their tokens), REQ-FUNC-013 (other organizations' tokens are 404), SRS Appendix A.
"""

import hashlib
import json
import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import ApiToken, Organization, User

URL = "/api/v1/tokens"


def make_org(name="Beispiel Bau GmbH"):
    return Organization.objects.create(
        name=name, address="Hauptstraße 1, 3500 Krems", vat_number="ATU12345678", terms_accepted_at=timezone.now()
    )


def make_user(email, organization, **roles):
    return User.objects.create_user(email=email, password="x", organization=organization, is_active=True, **roles)


@pytest.fixture
def org(db):
    return make_org()


@pytest.fixture
def admin(org):
    return make_user("admin@beispielbau.at", org, is_org_admin=True)


@pytest.fixture
def anna(org):
    return make_user("anna@beispielbau.at", org, is_request_user=True)


@pytest.fixture
def ben(org):
    return make_user("ben@beispielbau.at", org, is_review_user=True)


@pytest.fixture
def other_org_user(db):
    return make_user("eve@andere.at", make_org("Andere Bau GmbH"), is_org_admin=True, is_request_user=True)


def api_client(client, user):
    """Logged-in client that sends the CSRF header like the browser example in the README."""
    client.force_login(user)
    client.get(reverse("api_tokens"))  # sets the csrftoken cookie
    client.defaults["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
    return client


def post(client, body):
    return client.post(URL, data=json.dumps(body), content_type="application/json")


# --- Creating ---------------------------------------------------------------------------------------------------


def test_user_creates_own_token_and_sees_value_once(client, anna):
    client = api_client(client, anna)

    response = post(client, {"name": "ERP prod"})

    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    value = body["token"]
    # 40 random bytes in URL-safe base64; without the visible 8 characters still > 256 bits (REQ-SEC-002).
    assert len(value) == 54 and (len(value) - 8) * 6 >= 256
    assert body["prefix"] == value[:8]
    assert body["name"] == "ERP prod"
    assert body["owner"]["email"] == "anna@beispielbau.at"
    assert body["expiresAt"] is None and body["active"] is True

    token = ApiToken.objects.get()
    assert token.token_hash == hashlib.sha256(value.encode()).hexdigest()
    assert token.created_by == anna
    # The value is stored nowhere, and no later response contains it (REQ-FUNC-022).
    assert value not in json.dumps(list(ApiToken.objects.values()), default=str)
    assert value not in client.get(URL).content.decode()
    assert value not in client.get(reverse("api_tokens")).content.decode()


def test_each_token_value_is_different(client, anna):
    client = api_client(client, anna)
    values = {post(client, {"name": f"t{i}"}).json()["token"] for i in range(5)}
    assert len(values) == 5


def test_org_admin_creates_token_for_another_user(client, admin, anna):
    client = api_client(client, admin)

    response = post(client, {"name": "Anna's ERP", "userId": anna.pk})

    assert response.status_code == 201
    token = ApiToken.objects.get()
    assert token.user == anna and token.created_by == admin


def test_user_cannot_create_token_for_someone_else(client, anna, ben):
    client = api_client(client, anna)

    response = post(client, {"name": "sneaky", "userId": ben.pk})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert not ApiToken.objects.exists()


def test_org_admin_cannot_create_token_for_other_organization(client, admin, other_org_user):
    client = api_client(client, admin)

    response = post(client, {"name": "x", "userId": other_org_user.pk})

    assert response.status_code == 400
    assert "userId" in response.json()["error"]["fields"]
    assert not ApiToken.objects.exists()


def test_org_admin_cannot_create_token_for_deactivated_user(client, admin, anna):
    anna.is_active = False
    anna.save()
    client = api_client(client, admin)

    response = post(client, {"name": "x", "userId": anna.pk})

    assert response.status_code == 400
    assert not ApiToken.objects.exists()


def test_expiry_date_means_end_of_that_day(client, anna):
    client = api_client(client, anna)
    day = timezone.localdate() + timedelta(days=30)

    response = post(client, {"name": "temp", "expiresAt": day.isoformat()})

    assert response.status_code == 201
    expires_at = ApiToken.objects.get().expires_at
    assert timezone.localtime(expires_at).date() == day + timedelta(days=1)
    assert timezone.localtime(expires_at).hour == 0


def test_expiry_date_time_is_accepted(client, anna):
    client = api_client(client, anna)

    response = post(client, {"name": "temp", "expiresAt": "2099-01-01T12:00:00Z"})

    assert response.status_code == 201
    assert response.json()["expiresAt"] == "2099-01-01T12:00:00Z"


@pytest.mark.parametrize(
    "body, field",
    [
        ({}, "name"),
        ({"name": "   "}, "name"),
        ({"name": 5}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"name": "ok", "expiresAt": "tomorrow"}, "expiresAt"),
        ({"name": "ok", "expiresAt": "2020-01-01"}, "expiresAt"),
        ({"name": "ok", "expiresAt": 20991231}, "expiresAt"),
    ],
)
def test_invalid_input_is_rejected(client, anna, body, field):
    client = api_client(client, anna)

    response = post(client, body)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_INPUT" and field in error["fields"]
    assert not ApiToken.objects.exists()


def test_invalid_json_is_rejected(client, anna):
    client = api_client(client, anna)
    response = client.post(URL, data="{", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"


# --- Listing ----------------------------------------------------------------------------------------------------


def test_user_lists_only_own_tokens(client, anna, ben):
    ApiToken.issue(anna, "Anna's", created_by=anna)
    ApiToken.issue(ben, "Ben's", created_by=ben)
    client = api_client(client, anna)

    response = client.get(URL)

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["tokens"]] == ["Anna's"]


def test_org_admin_lists_all_tokens_of_organization_only(client, admin, anna, ben, other_org_user):
    ApiToken.issue(anna, "Anna's", created_by=anna)
    ApiToken.issue(ben, "Ben's", created_by=admin)
    ApiToken.issue(other_org_user, "Eve's", created_by=other_org_user)
    client = api_client(client, admin)

    names = {t["name"] for t in client.get(URL).json()["tokens"]}

    assert names == {"Anna's", "Ben's"}


def test_list_shows_only_metadata(client, anna):
    token, value = ApiToken.issue(anna, "ERP", created_by=anna)
    client = api_client(client, anna)

    entry = client.get(URL).json()["tokens"][0]

    assert set(entry) == {
        "id",
        "name",
        "prefix",
        "owner",
        "createdAt",
        "lastUsedAt",
        "expiresAt",
        "revokedAt",
        "active",
    }
    assert entry["prefix"] == value[:8]
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", entry["createdAt"])


# --- Revoking ---------------------------------------------------------------------------------------------------


def test_owner_revokes_own_token(client, anna):
    token, _ = ApiToken.issue(anna, "ERP", created_by=anna)
    client = api_client(client, anna)

    response = client.delete(f"{URL}/{token.pk}")

    assert response.status_code == 204
    token.refresh_from_db()
    assert token.revoked_at is not None and not token.is_active()
    assert client.get(URL).json()["tokens"][0]["active"] is False
    # Revoking twice is harmless.
    assert client.delete(f"{URL}/{token.pk}").status_code == 204


def test_org_admin_revokes_any_token_of_organization(client, admin, anna):
    token, _ = ApiToken.issue(anna, "ERP", created_by=anna)
    client = api_client(client, admin)

    assert client.delete(f"{URL}/{token.pk}").status_code == 204
    token.refresh_from_db()
    assert token.revoked_at is not None


def test_user_cannot_revoke_someone_elses_token(client, anna, ben):
    token, _ = ApiToken.issue(ben, "Ben's", created_by=ben)
    client = api_client(client, anna)

    assert client.delete(f"{URL}/{token.pk}").status_code == 404
    token.refresh_from_db()
    assert token.revoked_at is None


def test_token_of_other_organization_is_404(client, admin, other_org_user):
    token, _ = ApiToken.issue(other_org_user, "Eve's", created_by=other_org_user)
    client = api_client(client, admin)

    assert client.delete(f"{URL}/{token.pk}").status_code == 404
    assert client.post(reverse("revoke_api_token", args=[token.pk])).status_code == 404
    token.refresh_from_db()
    assert token.revoked_at is None


def test_deactivating_user_revokes_all_their_tokens(client, admin, anna, ben):
    anna_token, _ = ApiToken.issue(anna, "ERP", created_by=anna)
    ben_token, _ = ApiToken.issue(ben, "Ben's", created_by=ben)
    client.force_login(admin)

    client.post(reverse("deactivate_member", args=[anna.pk]))

    anna_token.refresh_from_db()
    ben_token.refresh_from_db()
    assert anna_token.revoked_at is not None
    assert ben_token.revoked_at is None

    # Reactivating the user does not bring the token back.
    client.post(reverse("reactivate_member", args=[anna.pk]))
    anna_token.refresh_from_db()
    assert not anna_token.is_active()


def test_deleting_user_deletes_their_tokens(client, admin, anna):
    ApiToken.issue(anna, "ERP", created_by=admin)
    client.force_login(admin)

    client.post(reverse("delete_member", args=[anna.pk]))

    assert not ApiToken.objects.exists()


def test_expired_token_is_not_active(anna):
    token, _ = ApiToken.issue(anna, "old", created_by=anna, expires_at=timezone.now() - timedelta(seconds=1))
    assert not token.is_active()


# --- Access rules of the endpoints ------------------------------------------------------------------------------


def test_anonymous_gets_401(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, data="{}", content_type="application/json").status_code == 401
    assert client.delete(f"{URL}/1").status_code == 401


def test_super_admin_without_organization_gets_403(client, db):
    root = User.objects.create_superuser("root@example.com", "x")
    client.force_login(root)
    assert client.get(URL).status_code == 403
    assert client.get(reverse("api_tokens")).status_code == 403


def test_session_call_without_csrf_header_is_rejected(client, anna):
    client.force_login(anna)
    client.handler.enforce_csrf_checks = True

    response = client.post(URL, data=json.dumps({"name": "x"}), content_type="application/json")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"
    assert not ApiToken.objects.exists()


def test_wrong_method_gets_405(client, anna):
    client = api_client(client, anna)
    response = client.put(URL)
    assert response.status_code == 405
    assert response["Allow"] == "GET, POST"


# --- Web page ---------------------------------------------------------------------------------------------------


def test_web_page_creates_token_and_shows_value_once(client, anna):
    client.force_login(anna)

    response = client.post(reverse("api_tokens"), {"name": "ERP prod", "owner": anna.pk})

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    token = ApiToken.objects.get()
    page = response.content.decode()
    value = re.search(r'id="new-token-value"[^>]* value="([^"]+)"', page).group(1)
    assert hashlib.sha256(value.encode()).hexdigest() == token.token_hash
    # Reloading the page does not show it again.
    assert value not in client.get(reverse("api_tokens")).content.decode()


def test_web_page_user_cannot_pick_another_owner(client, anna, ben):
    client.force_login(anna)

    response = client.post(reverse("api_tokens"), {"name": "sneaky", "owner": ben.pk})

    assert response.status_code == 200
    assert "owner" in response.context["form"].errors
    assert not ApiToken.objects.exists()


def test_web_page_org_admin_creates_token_with_expiry_for_member(client, admin, anna):
    client.force_login(admin)
    day = timezone.localdate() + timedelta(days=7)

    client.post(reverse("api_tokens"), {"name": "Anna ERP", "owner": anna.pk, "expires_on": day.isoformat()})

    token = ApiToken.objects.get()
    assert token.user == anna
    assert timezone.localtime(token.expires_at).date() == day + timedelta(days=1)


def test_web_page_rejects_past_expiry(client, anna):
    client.force_login(anna)
    yesterday = timezone.localdate() - timedelta(days=1)

    response = client.post(reverse("api_tokens"), {"name": "x", "owner": anna.pk, "expires_on": yesterday})

    assert "expires_on" in response.context["form"].errors
    assert not ApiToken.objects.exists()


def test_web_page_lists_tokens_and_revokes(client, admin, anna):
    token, value = ApiToken.issue(anna, "Anna ERP", created_by=anna)
    client.force_login(admin)

    page = client.get(reverse("api_tokens")).content.decode()
    assert "Anna ERP" in page and value[:8] in page and "anna@beispielbau.at" in page
    assert value not in page

    response = client.post(reverse("revoke_api_token", args=[token.pk]))

    assert response.status_code == 302
    token.refresh_from_db()
    assert token.revoked_at is not None


def test_web_page_requires_login(client):
    response = client.get(reverse("api_tokens"))
    assert response.status_code == 302
    assert reverse("login") in response["Location"]
