import pytest
from django.urls import reverse

from accounts.models import Organization, User


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


@pytest.fixture
def request_user(organization):
    return User.objects.create_user(
        email="requester@example.com",
        password="StrongPassword123!",
        organization=organization,
        is_active=True,
        is_request_user=True,
    )


@pytest.mark.django_db
def test_org_admin_can_view_team_members(client, org_admin, request_user):
    client.force_login(org_admin)

    response = client.get(reverse("team_members"))

    assert response.status_code == 200
    assert "admin@example.com" in response.content.decode()
    assert "requester@example.com" in response.content.decode()


@pytest.mark.django_db
def test_request_user_cannot_view_team_members(client, request_user):
    client.force_login(request_user)

    response = client.get(reverse("team_members"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_org_admin_can_edit_team_member(client, org_admin, request_user):
    client.force_login(org_admin)

    response = client.post(
        reverse("edit_member", args=[request_user.id]),
        {
            "first_name": "Updated",
            "last_name": "Member",
            "is_org_admin": "on",
            "is_request_user": "on",
            "is_review_user": "on",
        },
    )

    assert response.status_code == 302

    request_user.refresh_from_db()

    assert request_user.first_name == "Updated"
    assert request_user.last_name == "Member"
    assert request_user.is_org_admin is True
    assert request_user.is_request_user is True
    assert request_user.is_review_user is True


@pytest.mark.django_db
def test_org_admin_can_deactivate_member(client, org_admin, request_user):
    client.force_login(org_admin)

    response = client.post(reverse("deactivate_member", args=[request_user.id]))

    assert response.status_code == 302

    request_user.refresh_from_db()
    assert request_user.is_active is False


@pytest.mark.django_db
def test_org_admin_can_reactivate_member(client, org_admin, request_user):
    request_user.is_active = False
    request_user.save(update_fields=["is_active"])

    client.force_login(org_admin)

    response = client.post(reverse("reactivate_member", args=[request_user.id]))

    assert response.status_code == 302

    request_user.refresh_from_db()
    assert request_user.is_active is True


@pytest.mark.django_db
def test_org_admin_can_delete_team_member(client, org_admin, request_user):
    client.force_login(org_admin)

    response = client.post(reverse("delete_member", args=[request_user.id]))

    assert response.status_code == 302
    assert not User.objects.filter(id=request_user.id).exists()


@pytest.mark.django_db
def test_org_admin_cannot_access_other_organizations_members(client, org_admin):
    other_organization = Organization.objects.create(
        name="Other Company",
        address="Other Street 2",
        vat_number="ATU87654321",
        terms_accepted_at="2026-11-02T10:00:00Z",
        is_verified=True,
    )

    other_member = User.objects.create_user(
        email="other@example.com",
        password="StrongPassword123!",
        organization=other_organization,
        is_active=True,
        is_request_user=True,
    )

    client.force_login(org_admin)

    urls = [
        reverse("edit_member", args=[other_member.id]),
        reverse("deactivate_member", args=[other_member.id]),
        reverse("reactivate_member", args=[other_member.id]),
        reverse("delete_member", args=[other_member.id]),
    ]

    for url in urls:
        response = client.post(url)
        assert response.status_code == 404

    assert User.objects.filter(id=other_member.id).exists()


@pytest.mark.django_db
def test_cannot_deactivate_or_delete_last_admin_and_reviewer(client, org_admin):
    client.force_login(org_admin)

    deactivate_response = client.post(
        reverse("deactivate_member", args=[org_admin.id]),
        follow=True,
    )

    assert deactivate_response.status_code == 200
    assert any("last active Org Admin" in str(message) for message in deactivate_response.context["messages"])

    delete_response = client.post(
        reverse("delete_member", args=[org_admin.id]),
        follow=True,
    )

    assert delete_response.status_code == 200
    assert any("last active Org Admin" in str(message) for message in delete_response.context["messages"])

    org_admin.refresh_from_db()
    assert org_admin.is_active is True
    assert org_admin.is_org_admin is True
    assert org_admin.is_review_user is True


@pytest.mark.django_db
def test_member_actions_require_post(client, org_admin):
    client.force_login(org_admin)

    urls = [
        reverse("deactivate_member", args=[org_admin.id]),
        reverse("reactivate_member", args=[org_admin.id]),
        reverse("delete_member", args=[org_admin.id]),
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 405
