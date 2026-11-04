"""SCRUM-22: log in, log out, reset the password, lockout and session rules."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth import authenticate
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import config.settings as config_settings
from accounts import lockout
from accounts.models import Organization, User

EMAIL = "anna@musterbau.at"
PASSWORD = "Sicheres-Passwort-42"


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
        EMAIL, PASSWORD, first_name="Anna", organization=organization, is_org_admin=True, is_review_user=True
    )


def log_in(client, password=PASSWORD, email=EMAIL):
    return client.post(reverse("login"), {"username": email, "password": password})


def fail_logins(client, times):
    for _ in range(times):
        log_in(client, password="wrong-password")


def test_password_is_stored_only_as_salted_hash(user):
    assert PASSWORD not in user.password
    assert user.password.startswith(("pbkdf2_sha256$", "argon2$"))
    other = User.objects.create_user("bob@musterbau.at", PASSWORD)
    assert other.password != user.password  # same password, different salt


def test_log_in_and_out(client, user):
    assert log_in(client).status_code == 302
    assert client.get(reverse("home")).context["user"].is_authenticated

    client.post(reverse("logout"))
    assert not client.get(reverse("home")).context["user"].is_authenticated


def test_wrong_password_shows_generic_error(client, user):
    response = log_in(client, password="wrong-password")
    assert response.status_code == 200
    assert "Please enter a correct email address and password" in response.content.decode()


def test_account_locked_after_five_failures_even_with_correct_password(client, user):
    fail_logins(client, 5)

    response = log_in(client)
    assert response.status_code == 200
    assert "locked for 15 minutes" in response.content.decode()
    assert not client.get(reverse("home")).context["user"].is_authenticated


def test_four_failures_do_not_lock(client, user):
    fail_logins(client, 4)
    assert log_in(client).status_code == 302


def test_successful_login_resets_the_count(client, user):
    fail_logins(client, 4)
    assert log_in(client).status_code == 302
    client.post(reverse("logout"))

    fail_logins(client, 4)
    assert log_in(client).status_code == 302


def test_attempts_during_lock_do_not_extend_it(client, user):
    fail_logins(client, 8)
    assert lockout.failed_attempts(EMAIL) == lockout.MAX_FAILED_ATTEMPTS


def test_lock_ends_after_15_minutes(client, user, monkeypatch):
    fail_logins(client, 5)
    assert lockout.is_locked(EMAIL)

    later = timezone.now() + timedelta(minutes=15, seconds=1)
    monkeypatch.setattr("django.core.cache.backends.db.tz_now", lambda: later)
    assert log_in(client).status_code == 302


def test_lock_is_per_account_and_ignores_email_case(client, user):
    fail_logins(client, 5)
    assert lockout.is_locked(EMAIL.upper())
    assert not lockout.is_locked("someone-else@musterbau.at")


def test_lock_also_applies_outside_the_login_page(user, rf):
    """The admin login and any other authenticate() call go through the same backend."""
    for _ in range(5):
        assert authenticate(rf.post("/"), username=EMAIL, password="wrong-password") is None
    assert authenticate(rf.post("/"), username=EMAIL, password=PASSWORD) is None


def test_password_reset_by_email(client, user):
    response = client.post(reverse("password_reset"), {"email": EMAIL})
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    link = re.search(r"http://testserver(/password-reset/\S+/)", mail.outbox[0].body).group(1)

    # Django redirects the emailed link to a URL without the token before showing the form.
    form_url = client.get(link).url
    response = client.post(form_url, {"new_password1": "Neues-Passwort-77", "new_password2": "Neues-Passwort-77"})
    assert response.status_code == 302

    assert log_in(client, password="Neues-Passwort-77").status_code == 302
    client.post(reverse("logout"))
    assert log_in(client).status_code == 200  # the old password no longer works


def test_password_reset_does_not_reveal_unknown_addresses(client, user):
    response = client.post(reverse("password_reset"), {"email": "nobody@example.com"})
    assert response.status_code == 302
    assert len(mail.outbox) == 0


def test_session_ends_after_8_hours_of_inactivity_and_is_renewed(client, user, settings):
    assert settings.SESSION_COOKIE_AGE == 8 * 60 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST
    log_in(client)

    response = client.get(reverse("home"))
    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["max-age"] == 8 * 60 * 60  # sent again on every request, so inactivity counts


def test_session_cookie_flags(client, user, settings):
    cookie = log_in(client).cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    # Django forces settings.DEBUG off in tests, so compare with the debug mode the settings were loaded with.
    assert settings.SESSION_COOKIE_SECURE == (not config_settings.DEBUG)
    assert settings.CSRF_COOKIE_SECURE == (not config_settings.DEBUG)


def test_login_form_is_protected_against_csrf(user):
    client = Client(enforce_csrf_checks=True)
    assert log_in(client).status_code == 403
