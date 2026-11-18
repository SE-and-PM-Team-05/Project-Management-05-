import re
from datetime import timedelta

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Invitation, Organization, User


@pytest.fixture
def organization(db):
    return Organization.objects.create(
        name="Test Company",
        address="Test Street 1",
        vat_number="ATU12345678",
        terms_accepted_at="2026-11-02T10:00:00Z",
        is_verified=True,
    )


@pytest.fixture
def org_admin(organization):
    return User.objects.create_user(
        email="admin@example.com",
        password="StrongPassword123!",
        organization=organization,
        is_active=True,
        is_org_admin=True,
        is_request_user=True,
        is_review_user=True,
    )


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_org_admin_can_invite_member(client, org_admin, organization):
    """Verifies REQ-FUNC-010, REQ-COMP-006."""
    client.force_login(org_admin)

    response = client.post(
        reverse("invite_member"),
        {
            "email": "newmember@example.com",
            "is_request_user": "on",
        },
    )

    assert response.status_code == 302

    invitation = Invitation.objects.get(email="newmember@example.com")

    assert invitation.organization == organization
    assert invitation.is_request_user is True
    assert invitation.is_org_admin is False
    assert invitation.is_review_user is False

    assert len(mail.outbox) == 1
    assert "newmember@example.com" in mail.outbox[0].to
    assert "7 days" in mail.outbox[0].body


def invite(client, org_admin, email="newmember@example.com"):
    """Invite someone as Request User and return the path of the link in the email."""
    client.force_login(org_admin)
    client.post(reverse("invite_member"), {"email": email, "is_request_user": "on"})
    return re.search(r"http://testserver(/team/accept/[^ \n]+)", mail.outbox[-1].body).group(1)


def keycloak_user(email="newmember@example.com"):
    """A user as Keycloak's first login creates them: no organization, no roles, no password."""
    return User.objects.create_user(email=email, first_name="New", last_name="Member")


@pytest.mark.django_db
def test_invited_member_can_accept_invitation(client, org_admin, organization):
    """Verifies REQ-FUNC-010."""
    invitation_url = invite(client, org_admin)
    client.force_login(keycloak_user(email="NewMember@example.com"))

    assert "Test Company" in client.get(invitation_url).content.decode()
    response = client.post(invitation_url)
    assert response.status_code == 200

    new_member = User.objects.get(email__iexact="newmember@example.com")
    assert new_member.organization == organization
    assert new_member.is_request_user is True
    assert new_member.is_org_admin is False
    assert new_member.is_active is True

    assert Invitation.objects.get().accepted_at is not None


@pytest.mark.django_db
def test_accepting_requires_login_and_returns_to_the_invitation(client, org_admin):
    """Verifies REQ-FUNC-002, REQ-FUNC-010."""
    invitation_url = invite(client, org_admin)
    client.logout()

    response = client.get(invitation_url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("oidc_authentication_init"))
    assert "next=" in response.url


@pytest.mark.django_db
@pytest.mark.parametrize("case", ["other email", "already in an organization"])
def test_only_the_invited_email_without_organization_can_accept(client, org_admin, organization, case):
    """Verifies REQ-FUNC-010."""
    invitation_url = invite(client, org_admin)
    if case == "other email":
        member = keycloak_user(email="someone-else@example.com")
    else:
        member = keycloak_user()
        member.organization = Organization.objects.create(
            name="Other GmbH", address="x", vat_number="ATU87654321", terms_accepted_at=timezone.now()
        )
        member.save()
    client.force_login(member)

    assert client.post(invitation_url).status_code == 403
    member.refresh_from_db()
    assert member.organization != organization
    assert Invitation.objects.get().accepted_at is None


@pytest.mark.django_db
def test_user_without_organization_can_be_invited(client, org_admin):
    """Verifies REQ-FUNC-010."""
    keycloak_user()
    invite(client, org_admin)
    assert Invitation.objects.filter(email="newmember@example.com").exists()


@pytest.mark.django_db
def test_member_of_an_organization_cannot_be_invited(client, org_admin):
    """Verifies REQ-FUNC-010."""
    client.force_login(org_admin)
    response = client.post(reverse("invite_member"), {"email": "ADMIN@example.com", "is_request_user": "on"})
    assert response.status_code == 200
    assert not Invitation.objects.exists()


@pytest.mark.django_db
def test_expired_invitation_cannot_be_accepted(client, org_admin):
    """Verifies REQ-FUNC-010."""
    invitation_url = invite(client, org_admin, email="expired@example.com")
    Invitation.objects.update(expires_at=timezone.now() - timedelta(days=1))
    client.force_login(keycloak_user(email="expired@example.com"))

    assert client.post(invitation_url).status_code == 400
    assert User.objects.get(email="expired@example.com").organization is None


@pytest.mark.django_db
def test_accepted_invitation_cannot_be_reused(client, org_admin):
    """Verifies REQ-FUNC-010."""
    invitation_url = invite(client, org_admin, email="reused@example.com")
    client.force_login(keycloak_user(email="reused@example.com"))

    assert client.post(invitation_url).status_code == 200
    assert client.get(invitation_url).status_code == 400


@pytest.mark.django_db
def test_request_user_cannot_invite_members(client, organization):
    """Verifies REQ-FUNC-010, REQ-FUNC-012."""
    request_user = User.objects.create_user(
        email="requester@example.com",
        password="StrongPassword123!",
        organization=organization,
        is_active=True,
        is_request_user=True,
    )

    client.force_login(request_user)

    response = client.post(
        reverse("invite_member"),
        {
            "email": "newmember@example.com",
            "is_request_user": "on",
        },
    )

    assert response.status_code == 403

    assert not Invitation.objects.filter(email="newmember@example.com").exists()


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_duplicate_pending_invitation_is_rejected(client, org_admin):
    """Verifies REQ-FUNC-010."""
    client.force_login(org_admin)

    invitation_data = {
        "email": "duplicate@example.com",
        "is_request_user": "on",
    }

    first_response = client.post(
        reverse("invite_member"),
        invitation_data,
    )

    assert first_response.status_code == 302

    second_response = client.post(
        reverse("invite_member"),
        invitation_data,
    )

    assert second_response.status_code == 200

    assert Invitation.objects.filter(email="duplicate@example.com").count() == 1

    assert len(mail.outbox) == 1
