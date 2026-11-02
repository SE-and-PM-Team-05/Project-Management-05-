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


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_invited_member_can_accept_invitation(client, org_admin, organization):
    client.force_login(org_admin)

    client.post(
        reverse("invite_member"),
        {
            "email": "newmember@example.com",
            "is_request_user": "on",
        },
    )

    invitation = Invitation.objects.get(email="newmember@example.com")

    # Extract the invitation token from the email link.

    invitation_url = re.search(
        r"http://testserver(/team/accept/[^ \n]+)",
        mail.outbox[0].body,
    ).group(1)

    response = client.post(
        invitation_url,
        {
            "first_name": "New",
            "last_name": "Member",
            "password1": "StrongPassword123!",
            "password2": "StrongPassword123!",
        },
    )

    assert response.status_code == 200

    new_member = User.objects.get(email="newmember@example.com")

    assert new_member.organization == organization
    assert new_member.is_request_user is True
    assert new_member.is_active is True

    invitation.refresh_from_db()
    assert invitation.accepted_at is not None


@pytest.mark.django_db
def test_expired_invitation_cannot_be_accepted(client, org_admin, organization):
    client.force_login(org_admin)

    client.post(
        reverse("invite_member"),
        {
            "email": "expired@example.com",
            "is_request_user": "on",
        },
    )

    invitation = Invitation.objects.get(email="expired@example.com")

    invitation.expires_at = timezone.now() - timedelta(days=1)
    invitation.save(update_fields=["expires_at"])

    token = None

    import re

    match = re.search(
        r"/team/accept/([^/\s]+)",
        mail.outbox[-1].body,
    )
    token = match.group(1)

    response = client.get(reverse("accept_invitation", args=[token]))

    assert response.status_code == 400

    assert not User.objects.filter(email="expired@example.com").exists()


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_accepted_invitation_cannot_be_reused(client, org_admin):
    client.force_login(org_admin)

    client.post(
        reverse("invite_member"),
        {
            "email": "reused@example.com",
            "is_request_user": "on",
        },
    )

    import re

    match = re.search(
        r"/team/accept/([^/\s]+)",
        mail.outbox[-1].body,
    )
    token = match.group(1)

    invitation_url = reverse("accept_invitation", args=[token])

    data = {
        "first_name": "New",
        "last_name": "Member",
        "password1": "StrongPassword123!",
        "password2": "StrongPassword123!",
    }

    first_response = client.post(invitation_url, data)
    assert first_response.status_code == 200

    second_response = client.get(invitation_url)
    assert second_response.status_code == 400

    assert User.objects.filter(email="reused@example.com").count() == 1


@pytest.mark.django_db
def test_request_user_cannot_invite_members(client, organization):
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
