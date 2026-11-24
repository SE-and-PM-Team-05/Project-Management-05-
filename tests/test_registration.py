import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Organization, User
from accounts.validators import EU_PREFIXES, validate_vat_number

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
    """Verifies REQ-FUNC-001."""
    html = client.get(reverse("home")).content.decode()
    assert reverse("register") in html
    assert reverse("oidc_authentication_init") in html


# At least one valid example per country, built from the VIES FAQ table "VAT identification number
# structure" (SCRUM-56); several where a country has more than one format.
VALID_EXAMPLES = [
    "ATU12345678",
    "BE0123456789",
    "BE1123456789",
    "BG123456789",
    "BG1234567890",
    "CY12345678L",
    "CZ12345678",
    "CZ123456789",
    "CZ1234567890",
    "DE123456789",
    "DK12 34 56 78",
    "EE123456789",
    "EL123456789",
    "ESX1234567X",
    "ESA12345678",
    "ES12345678Z",
    "FI12345678",
    "FR12345678901",
    "FRAB123456789",
    "HR12345678901",
    "HU12345678",
    "IE1S12345L",
    "IE1234567WA",
    "IE1234567T",
    "IT12345678901",
    "LT123456789",
    "LT123456789012",
    "LU12345678",
    "LV12345678901",
    "MT12345678",
    "NL123456789B01",
    "PL1234567890",
    "PT123456789",
    "RO12",
    "RO1234567890",
    "SE123456789001",
    "SI12345678",
    "SK1234567890",
    "XI123456789",
    "XI123456789012",
    "XIGD123",
    "XIHA123",
]


@pytest.mark.parametrize("vat", VALID_EXAMPLES)
def test_valid_vat_formats(vat):
    """REQ-FUNC-001, REQ-FUNC-031: every format in the VIES structure table is accepted."""
    validate_vat_number(vat)


def test_every_country_has_a_valid_example():
    """REQ-FUNC-031: the list above covers every prefix VIES accepts."""
    assert {vat[:2] for vat in VALID_EXAMPLES} == EU_PREFIXES


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
        "ES123456789",  # first and last character both digits (VIES FAQ)
        "RO1",
        "LT1234567890",
        "IE1A34567WX",  # old Irish format with two trailing letters (VIES FAQ)
    ],
)
def test_malformed_vat_rejected(vat):
    """Verifies REQ-FUNC-001."""
    with pytest.raises(ValidationError):
        validate_vat_number(vat)


def test_registration_requires_login(client, db):
    """Verifies REQ-FUNC-001, REQ-FUNC-002."""
    response = client.get(reverse("register"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("oidc_authentication_init"))


def test_registration_creates_verified_org_with_all_roles(client, user):
    """Verifies REQ-FUNC-001."""
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
    """Verifies REQ-FUNC-001."""
    data = {**VALID}
    del data[field]
    response = client.post(reverse("register"), data)
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert not Organization.objects.exists()


def test_malformed_vat_rejected_in_form(client, user):
    """Verifies REQ-FUNC-001."""
    response = register(client, vat_number="ATU123")
    assert "vat_number" in response.context["form"].errors
    assert not Organization.objects.exists()


def test_user_with_organization_cannot_register_another(client, user):
    """Verifies REQ-FUNC-001."""
    register(client)
    response = register(client, organization_name="Other GmbH")
    assert response.status_code == 302
    assert Organization.objects.count() == 1


def test_super_admin_cannot_register_an_organization(client, db):
    """Verifies REQ-FUNC-001."""
    client.force_login(User.objects.create_superuser("admin@bizpartnercheck.at", "x"))
    register(client)
    assert not Organization.objects.exists()


def test_terms_page_states_no_liability(client):
    """Verifies REQ-COMP-003."""
    assert "no liability" in client.get(reverse("terms")).content.decode()
