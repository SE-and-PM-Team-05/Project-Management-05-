"""SCRUM-63: data model for the BMF fake-company list and the sync log (REQ-FUNC-072)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.urls import reverse

from accounts.models import Organization, User
from checks.models import FakeCompany, SyncLog

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 18, 3, 0, tzinfo=UTC)


def make_log(outcome=SyncLog.OUTCOME_SUCCESS, start=START, **fields):
    return SyncLog.objects.create(
        source=SyncLog.SOURCE_BMF,
        start_time=start,
        end_time=start + timedelta(seconds=4),
        outcome=outcome,
        **fields,
    )


def test_fake_company_stores_the_matching_fields():
    entry = FakeCompany.objects.create(
        name="Schein Bau GmbH",
        vat_number="ATU12345678",
        company_register_number="123456a",
        address="Hauptstraße 1, 1010 Wien",
        date_listed=date(2026, 11, 4),
    )

    stored = FakeCompany.objects.get(vat_number="ATU12345678")
    assert stored == entry
    assert stored.company_register_number == "123456a"
    assert str(stored) == "Schein Bau GmbH"


def test_fake_company_without_vat_or_fn_is_allowed():
    # 11 % of the feed's entries have neither; they can only be matched by name (docs/sources/bmf.md).
    entry = FakeCompany.objects.create(name="Max Muster", date_listed=date(2026, 11, 4))

    assert entry.vat_number == ""
    assert entry.company_register_number == ""


def test_req_func_072_sync_log_has_all_fields():
    log = make_log(number_of_entries=1703, feed_timestamp=datetime(2026, 11, 18, tzinfo=UTC))

    stored = SyncLog.objects.get(pk=log.pk)
    assert stored.source == "BMF"
    assert stored.start_time == START
    assert stored.end_time == START + timedelta(seconds=4)
    assert stored.outcome == "success"
    assert stored.number_of_entries == 1703
    assert stored.feed_timestamp == datetime(2026, 11, 18, tzinfo=UTC)


def test_req_func_072_failed_run_is_logged_with_its_error():
    log = make_log(outcome=SyncLog.OUTCOME_FAILED, error_message="HTTP_503")

    assert log.feed_timestamp is None
    assert log.number_of_entries == 0
    assert log.error_message == "HTTP_503"


def test_sync_log_lists_newest_run_first():
    older = make_log(start=START - timedelta(days=1))
    newer = make_log()

    assert list(SyncLog.objects.all()) == [newer, older]


def test_last_success_ignores_failed_runs():
    success = make_log(start=START - timedelta(days=1))
    make_log(outcome=SyncLog.OUTCOME_FAILED)

    assert SyncLog.last_success(SyncLog.SOURCE_BMF) == success


def test_last_success_is_none_before_the_first_sync():
    assert SyncLog.last_success(SyncLog.SOURCE_BMF) is None


def test_req_func_072_organization_users_cannot_open_the_sync_log(client):
    org = Organization.objects.create(
        name="Beispiel Bau GmbH",
        address="Hauptstraße 1",
        vat_number="ATU99999999",
        is_verified=True,
        terms_accepted_at=START,
    )
    user = User.objects.create_user("anna@beispielbau.at", "x", organization=org, is_org_admin=True)
    client.force_login(user)

    response = client.get(reverse("admin:checks_synclog_changelist"))

    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.parametrize("model", ["synclog", "fakecompany"])
def test_req_func_072_operator_can_view_but_not_change(client, model):
    log = make_log()
    entry = FakeCompany.objects.create(name="Schein Bau GmbH", date_listed=date(2026, 11, 4))
    client.force_login(User.objects.create_superuser("root@example.com", "x"))
    pk = log.pk if model == "synclog" else entry.pk

    assert client.get(reverse(f"admin:checks_{model}_changelist")).status_code == 200
    assert client.get(reverse(f"admin:checks_{model}_add")).status_code == 403
    assert client.get(reverse(f"admin:checks_{model}_delete", args=[pk])).status_code == 403
    # The change page opens read-only, without a save button.
    page = client.get(reverse(f"admin:checks_{model}_change", args=[pk]))
    assert page.status_code == 200
    assert b'name="_save"' not in page.content
