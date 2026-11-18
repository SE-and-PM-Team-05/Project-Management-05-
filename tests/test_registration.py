import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Organization, User
from accounts.validators import validate_vat_number

VALID = {
    "organization_name": "Muster Bau GmbH",
    "address": "Hauptstraße 1, 3500 Krems",
    "vat_number": "ATU 1234 5678",
    "accept_terms": "on",
}


@pytest.fixture
def user(db, client):
    """Logged in through Keycloak for the first time: no organization yet."""
    user = User.objects.create_user("anna@musterbau.at", first_name="Anna", last_name="Muster")
    client.force_login(user)
    return user


def register(client, **changes):
    return client.post(reverse("register"), {**VALID, **changes})


def test_landing_page_offers_register_and_login(client):
    html = client.get(reverse("home")).content.decode()
    assert reverse("register") in html
    assert reverse("oidc_authentication_init") in html


@pytest.mark.parametrize(
    "vat",
    [
        "ATU12345678",
        "DE123456789",
        "FR12345678901",
        "NL123456789B01",
        "BE0123456789",
        "EL123456789",
        "ESX1234567X",
        "IE1234567WA",
        "XIGD123",
    ],
)
def test_valid_vat_formats(vat):
    validate_vat_number(vat)


@pytest.mark.parametrize(
    "vat",
    [
        "U12345678",
        "AT12345678",
        "ATU1234567",
        "DE12345678",
        "US123456789",
        "",
        "GR123456789",
        "BE2123456789",
        "NL123456789",
        "FR123",
        "ITABCDEFGHIJK",
    ],
)
def test_malformed_vat_rejected(vat):
    with pytest.raises(ValidationError):
        validate_vat_number(vat)


def test_registration_requires_login(client, db):
    response = client.get(reverse("register"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("oidc_authentication_init"))


def test_registration_creates_verified_org_with_all_roles(client, user):
    response = register(client)
    assert response.status_code == 302

    org = Organization.objects.get()
    assert org.vat_number == "ATU12345678"
    assert org.is_verified  # Keycloak only lets verified email addresses log in
    assert org.terms_accepted_at is not None

    user.refresh_from_db()
    assert user.organization == org
    assert user.is_org_admin and user.is_request_user and user.is_review_user


@pytest.mark.parametrize("field", ["organization_name", "address", "vat_number", "accept_terms"])
def test_missing_field_rejected(client, user, field):
    data = {**VALID}
    del data[field]
    response = client.post(reverse("register"), data)
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert not Organization.objects.exists()


def test_malformed_vat_rejected_in_form(client, user):
    response = register(client, vat_number="ATU123")
    assert "vat_number" in response.context["form"].errors
    assert not Organization.objects.exists()


def test_user_with_organization_cannot_register_another(client, user):
    register(client)
    response = register(client, organization_name="Other GmbH")
    assert response.status_code == 302
    assert Organization.objects.count() == 1


def test_super_admin_cannot_register_an_organization(client, db):
    client.force_login(User.objects.create_superuser("admin@bizpartnercheck.at", "x"))
    register(client)
    assert not Organization.objects.exists()


def test_terms_page_states_no_liability(client):
    assert "no liability" in client.get(reverse("terms")).content.decode()
