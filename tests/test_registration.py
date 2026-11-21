from unittest import mock

import pytest
import requests
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Organization, User
from accounts.validators import validate_vat_number
from checks.sources.vies import VIES_URL

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


def vies_answer(status=200, **body):
    response = mock.Mock(status_code=status)
    response.json.return_value = body
    return response


VIES_VALID = vies_answer(countryCode="AT", vatNumber="U12345678", valid=True, name="MUSTER BAU GMBH", address="---")
VIES_INVALID = vies_answer(countryCode="AT", vatNumber="U12345678", valid=False, name="---", address="---")


@pytest.fixture(autouse=True)
def vies():
    """VIES is never called for real; by default it confirms the number. Tests change return_value/side_effect."""
    with mock.patch("checks.sources.http.requests.post", return_value=VIES_VALID) as post:
        yield post


def register(client, **changes):
    return client.post(reverse("register"), {**VALID, **changes})


def test_landing_page_offers_register_and_login(client):
    """Verifies REQ-FUNC-001."""
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
    """Verifies REQ-FUNC-001."""
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


def test_malformed_vat_rejected_in_form(client, user, vies):
    """Verifies REQ-FUNC-001, REQ-FUNC-004."""
    response = register(client, vat_number="ATU123")
    assert "vat_number" in response.context["form"].errors
    assert not Organization.objects.exists()
    vies.assert_not_called()  # a malformed number is rejected before VIES is asked


# --- VIES check of the organization's own VAT number (REQ-FUNC-004, SCRUM-52) ---


def test_vat_number_confirmed_by_vies_is_verified(client, user, vies):
    """REQ-FUNC-004: VIES is asked about the normalized number, and a valid answer marks it verified."""
    response = register(client)
    assert response.status_code == 302

    org = Organization.objects.get()
    assert org.vat_verified_at is not None
    assert not org.vat_unverified
    vies.assert_called_once()
    assert vies.call_args.args == (VIES_URL,)
    assert vies.call_args.kwargs["json"] == {"countryCode": "AT", "vatNumber": "U12345678"}
    assert not list(get_messages(response.wsgi_request))


def test_vat_number_invalid_in_vies_is_rejected(client, user, vies):
    """REQ-FUNC-004: an invalid number is rejected with a clear message and nothing is created."""
    vies.return_value = VIES_INVALID
    response = register(client)

    assert response.status_code == 200
    errors = response.context["form"].errors["vat_number"]
    assert errors == [
        "VIES, the EU's VAT number register, reports ATU12345678 as not valid. "
        "Enter your organization's own VAT number exactly as it appears on your invoices."
    ]
    assert "reports ATU12345678 as not valid" in response.content.decode()
    assert not Organization.objects.exists()
    user.refresh_from_db()
    assert user.organization is None
    assert not (user.is_org_admin or user.is_request_user or user.is_review_user)


@pytest.mark.parametrize(
    "answers",
    [
        [requests.Timeout(), requests.Timeout()],
        [requests.ConnectionError(), requests.ConnectionError()],
        [vies_answer(status=503), vies_answer(status=503)],
        [vies_answer(actionSucceed=False, errorWrappers=[{"error": "MS_UNAVAILABLE"}])],
        [vies_answer(userError="MS_MAX_CONCURRENT_REQ", valid=False)],
        [vies_answer(status=200)],  # no boolean "valid"
    ],
    ids=["timeout", "network-error", "http-503", "member-state-down", "overloaded", "invalid-response"],
)
def test_vies_unavailable_registers_as_vat_unverified(client, user, vies, answers):
    """REQ-FUNC-004: if VIES gives no usable answer, the organization is registered and marked "VAT unverified"."""
    vies.return_value = None
    vies.side_effect = answers
    response = register(client)

    assert response.status_code == 302
    org = Organization.objects.get()
    assert org.vat_verified_at is None
    assert org.vat_unverified
    user.refresh_from_db()
    assert user.organization == org and user.is_org_admin

    shown = response.client.get(response.url).content.decode()
    assert "marked “VAT unverified”" in shown


def test_vies_answer_after_one_retry_counts_as_verified(client, user, vies):
    """REQ-FUNC-004: a transient VIES error is retried once (REQ-REL-003) before the number counts as unverified."""
    vies.side_effect = [requests.Timeout(), VIES_VALID]
    register(client)
    assert Organization.objects.get().vat_verified_at is not None
    assert vies.call_count == 2


def test_operator_can_filter_vat_unverified_organizations(client, db):
    """REQ-FUNC-004: the Super Admin finds the organizations marked "VAT unverified" in the admin."""
    common = {"address": "x", "terms_accepted_at": timezone.now()}
    Organization.objects.create(
        name="Checked Bau GmbH", vat_number="ATU11111111", vat_verified_at=timezone.now(), **common
    )
    Organization.objects.create(name="Unchecked Bau GmbH", vat_number="ATU22222222", **common)
    client.force_login(User.objects.create_superuser("admin@bizpartnercheck.at", "x"))

    url = reverse("admin:accounts_organization_changelist")
    unverified = client.get(url, {"vat": "unverified"}).content.decode()
    assert "Unchecked Bau GmbH" in unverified and "Checked Bau GmbH" not in unverified
    verified = client.get(url, {"vat": "verified"}).content.decode()
    assert "Checked Bau GmbH" in verified and "Unchecked Bau GmbH" not in verified


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
