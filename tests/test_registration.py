import re
import time
from unittest import mock

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Organization, User
from accounts.validators import validate_vat_number
from accounts.verification import LINK_MAX_AGE

VALID = {
    "organization_name": "Muster Bau GmbH",
    "address": "Hauptstraße 1, 3500 Krems",
    "vat_number": "ATU 1234 5678",
    "first_name": "Anna",
    "last_name": "Muster",
    "email": "anna@musterbau.at",
    "password1": "Sicheres-Passwort-42",
    "password2": "Sicheres-Passwort-42",
    "accept_terms": "on",
}


def register(client, **changes):
    return client.post(reverse("register"), {**VALID, **changes})


def verification_link():
    return re.search(r"http://testserver(/verify/\S+/)", mail.outbox[-1].body).group(1)


def test_landing_page_offers_register_and_login(client):
    html = client.get(reverse("home")).content.decode()
    assert reverse("register") in html
    assert reverse("login") in html


@pytest.mark.parametrize("vat", ["ATU12345678", "DE123456789", "FR12345678901", "NL123456789B01"])
def test_valid_vat_formats(vat):
    validate_vat_number(vat)


@pytest.mark.parametrize("vat", ["U12345678", "AT12345678", "ATU1234567", "DE12345678", "US123456789", ""])
def test_malformed_vat_rejected(vat):
    with pytest.raises(ValidationError):
        validate_vat_number(vat)


@pytest.mark.django_db
def test_registration_creates_unverified_org_with_all_roles(client):
    response = register(client)
    assert response.status_code == 302

    org = Organization.objects.get()
    assert org.vat_number == "ATU12345678"
    assert not org.is_verified
    assert org.terms_accepted_at is not None

    user = User.objects.get()
    assert user.organization == org
    assert user.is_org_admin and user.is_request_user and user.is_review_user
    assert not user.is_active
    assert user.check_password(VALID["password1"])
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field",
    ["organization_name", "address", "vat_number", "first_name", "last_name", "email", "password1", "accept_terms"],
)
def test_missing_field_rejected(client, field):
    data = {**VALID}
    del data[field]
    response = client.post(reverse("register"), data)
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert not Organization.objects.exists()


@pytest.mark.django_db
def test_malformed_vat_rejected_in_form(client):
    response = register(client, vat_number="ATU123")
    assert "vat_number" in response.context["form"].errors
    assert not Organization.objects.exists()


@pytest.mark.django_db
def test_duplicate_email_rejected(client):
    register(client)
    response = register(client, email="ANNA@musterbau.at", organization_name="Other GmbH")
    assert "email" in response.context["form"].errors
    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_unverified_admin_cannot_log_in_until_link_opened(client):
    register(client)
    credentials = {"username": VALID["email"], "password": VALID["password1"]}
    assert not client.login(email=VALID["email"], password=VALID["password1"])

    response = client.get(verification_link())
    assert response.status_code == 200
    assert Organization.objects.get().is_verified

    response = client.post(reverse("login"), credentials)
    assert response.status_code == 302


@pytest.mark.django_db
def test_expired_link_offers_resend(client):
    register(client)
    link = verification_link()

    with mock.patch("django.core.signing.time.time", return_value=time.time() + LINK_MAX_AGE + 1):
        response = client.get(link)
    assert response.status_code == 400
    assert response.context["expired"]
    assert reverse("resend_verification") in response.content.decode()
    assert not Organization.objects.get().is_verified


@pytest.mark.django_db
def test_tampered_link_rejected(client):
    register(client)
    response = client.get(verification_link().replace(":", "x", 1))
    assert response.status_code == 400
    assert not Organization.objects.get().is_verified


@pytest.mark.django_db
def test_resend_sends_new_link_that_works(client):
    register(client)
    client.post(reverse("resend_verification"), {"email": VALID["email"]})
    assert len(mail.outbox) == 2
    client.get(verification_link())
    assert Organization.objects.get().is_verified


@pytest.mark.django_db
def test_resend_does_not_reveal_unknown_addresses(client):
    response = client.post(reverse("resend_verification"), {"email": "nobody@example.com"})
    assert response.status_code == 200
    assert len(mail.outbox) == 0


def test_terms_page_states_no_liability(client):
    assert "no liability" in client.get(reverse("terms")).content.decode()
