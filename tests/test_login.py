"""Login through Keycloak, the admin's password login with lockout, and session rules (SCRUM-22)."""

import threading
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import authenticate
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

import config.settings as config_settings
from accounts import lockout
from accounts.backends import KeycloakBackend
from accounts.models import Organization, User

EMAIL = "anna@musterbau.at"
ADMIN_EMAIL = "admin@bizpartnercheck.at"
PASSWORD = "Sicheres-Passwort-42"
CLAIMS = {"email": EMAIL, "email_verified": True, "given_name": "Anna", "family_name": "Muster"}


@pytest.fixture
def user(db):
    organization = Organization.objects.create(
        name="Muster Bau GmbH",
        address="Hauptstraße 1, 3500 Krems",
        vat_number="ATU12345678",
        is_verified=True,
        terms_accepted_at=timezone.now(),
    )
    return User.objects.create_user(
        EMAIL, first_name="Anna", organization=organization, is_org_admin=True, is_review_user=True
    )


@pytest.fixture
def admin(db):
    return User.objects.create_superuser(ADMIN_EMAIL, PASSWORD)


@pytest.fixture
def clock(monkeypatch):
    """Call clock(minutes=…) to make timezone.now() return that much later than the start of the test."""
    start = timezone.now()
    now = {"value": start}
    monkeypatch.setattr("django.utils.timezone.now", lambda: now["value"])

    def move_to(**offset):
        now["value"] = start + timedelta(**offset)

    return move_to


def keycloak_login(client, claims=CLAIMS, next_url=None):
    """Run the real login and callback views, with Keycloak's token and userinfo answers mocked."""
    start = reverse("oidc_authentication_init") + (f"?next={next_url}" if next_url else "")
    state = parse_qs(urlparse(client.get(start).url).query)["state"][0]
    with (
        mock.patch.object(KeycloakBackend, "get_token", return_value={"id_token": "id-token", "access_token": "a"}),
        mock.patch.object(KeycloakBackend, "verify_token", return_value={"sub": "1"}),
        mock.patch.object(KeycloakBackend, "get_userinfo", return_value=claims),
    ):
        return client.get(reverse("oidc_authentication_callback"), {"code": "code", "state": state})


def is_logged_in(client):
    return client.get(reverse("home")).context["user"].is_authenticated


def admin_login(client, password=PASSWORD, email=ADMIN_EMAIL):
    return client.post(reverse("admin:login"), {"username": email, "password": password, "next": "/admin/"})


def fail_admin_logins(client, times):
    for _ in range(times):
        admin_login(client, password="wrong-password")


# Keycloak


def test_login_sends_the_user_to_keycloak(client, db, settings):
    """Verifies REQ-FUNC-003."""
    url = urlparse(client.get(reverse("oidc_authentication_init")).url)
    assert f"{url.scheme}://{url.netloc}{url.path}" == settings.OIDC_OP_AUTHORIZATION_ENDPOINT
    query = parse_qs(url.query)
    assert query["client_id"] == [settings.OIDC_RP_CLIENT_ID]
    assert query["scope"] == ["openid email profile"]


def test_login_pages_link_to_keycloak(client):
    """Verifies REQ-FUNC-003."""
    html = client.get(reverse("home")).content.decode()
    assert reverse("oidc_authentication_init") in html


def test_existing_user_logs_in_by_email(client, user):
    """Verifies REQ-FUNC-003."""
    response = keycloak_login(client, claims={**CLAIMS, "email": EMAIL.upper()})
    assert response.status_code == 302
    assert response.url == reverse("home")
    assert client.get(reverse("home")).context["user"] == user


def test_first_login_creates_user_without_organization_or_password(client, db):
    """Verifies REQ-FUNC-003."""
    keycloak_login(client)
    user = User.objects.get()
    assert (user.email, user.first_name, user.last_name) == (EMAIL, "Anna", "Muster")
    assert user.organization is None
    assert not (user.is_org_admin or user.is_request_user or user.is_review_user)
    assert not user.has_usable_password()
    assert "Register your organization" in client.get(reverse("home")).content.decode()


def test_unverified_email_is_refused(client, db):
    """Verifies REQ-FUNC-002."""
    keycloak_login(client, claims={**CLAIMS, "email_verified": False})
    assert not is_logged_in(client)
    assert not User.objects.exists()


def test_deactivated_member_is_refused(client, user):
    """Verifies REQ-FUNC-003, REQ-FUNC-010."""
    user.is_active = False
    user.save()
    keycloak_login(client)
    assert not is_logged_in(client)


def test_staff_account_cannot_log_in_through_keycloak(client, admin):
    """Verifies REQ-FUNC-003."""
    keycloak_login(client, claims={**CLAIMS, "email": ADMIN_EMAIL})
    assert not is_logged_in(client)


def test_login_returns_to_the_page_that_asked_for_it(client, user):
    """Verifies REQ-FUNC-003."""
    response = keycloak_login(client, next_url=reverse("team_members"))
    assert response.url == reverse("team_members")


def test_logout_also_ends_the_keycloak_session(client, user, settings):
    """Verifies REQ-FUNC-003."""
    keycloak_login(client)
    response = client.post(reverse("oidc_logout"))
    assert response.url.startswith(settings.OIDC_OP_LOGOUT_ENDPOINT + "?")
    query = parse_qs(urlparse(response.url).query)
    assert query["id_token_hint"] == ["id-token"]
    assert query["post_logout_redirect_uri"] == ["http://testserver/"]
    assert not is_logged_in(client)


def test_deactivating_a_member_ends_their_open_session(client, user):
    """Verifies REQ-FUNC-010."""
    keycloak_login(client)
    assert is_logged_in(client)

    User.objects.filter(pk=user.pk).update(is_active=False)
    assert not is_logged_in(client)


def test_superuser_without_staff_flag_cannot_log_in_through_keycloak(client, admin):
    """Verifies REQ-FUNC-003."""
    User.objects.filter(pk=admin.pk).update(is_staff=False)
    keycloak_login(client, claims={**CLAIMS, "email": ADMIN_EMAIL})
    assert not is_logged_in(client)


# Admin password login with lockout (REQ-SEC-004)


def test_password_is_stored_only_as_salted_hash(admin):
    """Verifies REQ-SEC-002."""
    assert PASSWORD not in admin.password
    assert admin.password.startswith(("pbkdf2_sha256$", "argon2$"))
    other = User.objects.create_superuser("other@bizpartnercheck.at", PASSWORD)
    assert other.password != admin.password  # same password, different salt


def test_admin_logs_in_with_password(client, admin):
    """Verifies REQ-FUNC-005."""
    assert admin_login(client).status_code == 302
    assert client.get(reverse("admin:index")).status_code == 200


def test_admin_account_locked_after_five_failures_even_with_correct_password(client, admin):
    """Verifies REQ-SEC-004."""
    fail_admin_logins(client, 5)
    assert admin_login(client).status_code == 200
    assert not is_logged_in(client)


def test_four_failures_do_not_lock(client, admin):
    """Verifies REQ-SEC-004."""
    fail_admin_logins(client, 4)
    assert admin_login(client).status_code == 302


def test_successful_login_resets_the_count(client, admin):
    """Verifies REQ-SEC-004."""
    fail_admin_logins(client, 4)
    assert admin_login(client).status_code == 302
    client.post(reverse("admin:logout"))

    fail_admin_logins(client, 4)
    assert admin_login(client).status_code == 302


def test_attempts_during_lock_do_not_extend_it(client, admin):
    """Verifies REQ-SEC-004."""
    fail_admin_logins(client, 8)
    assert lockout.failed_attempts(ADMIN_EMAIL) == lockout.MAX_FAILED_ATTEMPTS


def test_lock_ends_after_15_minutes(client, admin, clock):
    """Verifies REQ-SEC-004."""
    fail_admin_logins(client, 5)
    assert lockout.is_locked(ADMIN_EMAIL)

    clock(minutes=15, seconds=1)
    assert admin_login(client).status_code == 302


def test_attempts_during_lock_do_not_move_its_end(db, clock):
    """REQ-SEC-004: the lock ends 15 minutes after the 5th failure, however many attempts follow it."""
    for _ in range(5):
        lockout.record_failure(ADMIN_EMAIL)
    clock(minutes=10)
    for _ in range(3):
        lockout.record_failure(ADMIN_EMAIL)
    assert lockout.failed_attempts(ADMIN_EMAIL) == lockout.MAX_FAILED_ATTEMPTS

    clock(minutes=14, seconds=59)
    assert lockout.is_locked(ADMIN_EMAIL)
    clock(minutes=15, seconds=1)
    assert not lockout.is_locked(ADMIN_EMAIL)


def test_each_counted_failure_restarts_the_window(db, clock):
    """REQ-SEC-004: failures add up as long as each comes within 15 minutes of the previous one."""
    for _ in range(4):
        lockout.record_failure(ADMIN_EMAIL)
    clock(minutes=10)
    lockout.record_failure(ADMIN_EMAIL)
    assert lockout.is_locked(ADMIN_EMAIL)
    clock(minutes=24, seconds=59)  # 15 minutes are counted from the 5th failure, not the 1st
    assert lockout.is_locked(ADMIN_EMAIL)


def test_failures_older_than_15_minutes_are_forgotten(db, clock):
    """REQ-SEC-004: after 15 minutes without a failure the count starts again at 1."""
    for _ in range(4):
        lockout.record_failure(ADMIN_EMAIL)
    clock(minutes=15, seconds=1)
    assert lockout.failed_attempts(ADMIN_EMAIL) == 0
    lockout.record_failure(ADMIN_EMAIL)
    assert lockout.failed_attempts(ADMIN_EMAIL) == 1


def test_failure_is_counted_in_one_update_without_reading_the_count(db):
    """REQ-SEC-004: the increment happens in the database, so no other login can slip in between (SCRUM-54)."""
    lockout.record_failure(ADMIN_EMAIL)
    with CaptureQueriesContext(connection) as queries:
        lockout.record_failure(ADMIN_EMAIL)
    statements = [q["sql"].split()[0].upper() for q in queries.captured_queries]
    assert statements == ["INSERT", "UPDATE"]  # INSERT … ON CONFLICT DO NOTHING; no SELECT of the count
    assert lockout.failed_attempts(ADMIN_EMAIL) == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("threads", "expected"), [(4, 4), (8, lockout.MAX_FAILED_ATTEMPTS)])
def test_simultaneous_failures_are_each_counted(threads, expected):
    """REQ-SEC-004: failed logins that arrive at the same moment are all counted, up to the limit (SCRUM-54)."""
    start = threading.Barrier(threads)
    errors = []

    def fail_once():
        try:
            start.wait()
            lockout.record_failure(ADMIN_EMAIL)
        except Exception as error:  # reported below; an exception in a thread would otherwise be lost
            errors.append(error)
        finally:
            connection.close()  # each thread has its own database connection

    workers = [threading.Thread(target=fail_once) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert not errors
    assert lockout.failed_attempts(ADMIN_EMAIL) == expected


def test_lock_is_per_account_and_ignores_email_case(client, admin):
    """Verifies REQ-SEC-004."""
    fail_admin_logins(client, 5)
    assert lockout.is_locked(ADMIN_EMAIL.upper())
    assert not lockout.is_locked("someone-else@musterbau.at")


def test_lock_also_applies_outside_the_admin_login_page(admin, rf):
    """Verifies REQ-SEC-004."""
    for _ in range(5):
        assert authenticate(rf.post("/"), username=ADMIN_EMAIL, password="wrong-password") is None
    assert authenticate(rf.post("/"), username=ADMIN_EMAIL, password=PASSWORD) is None


# Sessions (REQ-SEC-006)


def test_session_ends_after_8_hours_of_inactivity_and_is_renewed(client, user, settings):
    """Verifies REQ-SEC-006."""
    assert settings.SESSION_COOKIE_AGE == 8 * 60 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST
    keycloak_login(client)

    response = client.get(reverse("home"))
    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["max-age"] == 8 * 60 * 60  # sent again on every request, so inactivity counts


def test_session_cookie_flags(client, user, settings):
    """Verifies REQ-SEC-006."""
    cookie = keycloak_login(client).cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    # Django forces settings.DEBUG off in tests, so compare with the debug mode the settings were loaded with.
    assert settings.SESSION_COOKIE_SECURE == (not config_settings.DEBUG)
    assert settings.CSRF_COOKIE_SECURE == (not config_settings.DEBUG)


def test_logout_is_protected_against_csrf(user):
    """Verifies REQ-SEC-006."""
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post(reverse("oidc_logout")).status_code == 403
