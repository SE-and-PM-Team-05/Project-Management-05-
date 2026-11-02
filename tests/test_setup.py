import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from accounts.models import User
from config.settings import parse_database_url


def test_parse_database_url():
    db = parse_database_url("postgres://app:p%40ss@db.example.com:6543/bpc")
    assert db["NAME"] == "bpc"
    assert db["USER"] == "app"
    assert db["PASSWORD"] == "p@ss"
    assert db["HOST"] == "db.example.com"
    assert db["PORT"] == "6543"


def test_home_and_healthz(client):
    assert client.get(reverse("home")).status_code == 200
    assert client.get(reverse("healthz")).content == b"ok"


@pytest.mark.django_db
def test_create_superadmin_only_once(capsys):
    call_command("create_superadmin", "admin@example.com")
    out = capsys.readouterr().out
    password = out.split("One-time password: ")[1].split()[0]

    admin = User.objects.get()
    assert admin.is_superuser and admin.is_staff
    assert admin.must_change_password
    assert admin.check_password(password)

    with pytest.raises(CommandError):
        call_command("create_superadmin", "second@example.com")
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_one_time_password_must_be_changed(client):
    call_command("create_superadmin", "admin@example.com")
    admin = User.objects.get()
    admin.set_password("one-time")
    admin.must_change_password = True
    admin.save()
    client.force_login(admin)

    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert response.url == reverse("admin:password_change")

    response = client.post(
        reverse("admin:password_change"),
        {"old_password": "one-time", "new_password1": "Tr1cky-new-pass", "new_password2": "Tr1cky-new-pass"},
    )
    assert response.status_code == 302
    admin.refresh_from_db()
    assert not admin.must_change_password
    assert client.get(reverse("admin:index")).status_code == 200
