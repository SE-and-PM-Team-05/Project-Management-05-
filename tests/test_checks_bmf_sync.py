"""SCRUM-64: the daily BMF import (REQ-FUNC-070, REQ-FUNC-072, REQ-FUNC-073, REQ-REL-002). No network needed."""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from checks.models import FakeCompany, SyncLog
from checks.sources import bmf_feed
from checks.sources.bmf_feed import FeedError
from checks.sync import sync_bmf

from .bmf_samples import COMPANY, SAMPLE, feed, item

pytestmark = pytest.mark.django_db

YESTERDAY = datetime(2026, 11, 17, 3, 17, tzinfo=UTC)


@pytest.fixture
def last_good_copy():
    """Yesterday's successful sync with one entry, which a failed run must keep."""
    entry = FakeCompany.objects.create(name="Alt Bau GmbH", vat_number="ATU11111111", date_listed=date(2026, 1, 5))
    log = SyncLog.objects.create(
        source=SyncLog.SOURCE_BMF,
        start_time=YESTERDAY,
        end_time=YESTERDAY + timedelta(seconds=5),
        outcome=SyncLog.OUTCOME_SUCCESS,
        number_of_entries=1,
        feed_timestamp=date(2026, 11, 17),
    )
    return entry, log


def serve(xml_bytes):
    return lambda: xml_bytes


def fail_with(code):
    def download():
        raise FeedError(code)

    return download


def companies(count):
    return feed(*(item(f"Firma {number} GmbH", COMPANY) for number in range(count)))


def test_req_func_070_import_stores_every_entry():
    log = sync_bmf(download=serve(SAMPLE))

    assert log.outcome == SyncLog.OUTCOME_SUCCESS
    stored = FakeCompany.objects.get(vat_number="ATU12345678")
    assert (stored.name, stored.company_register_number, stored.address, stored.date_listed) == (
        "Schein Bau & Co GmbH",
        "123456a",
        "Hauptstraße 1, 1010 Wien",
        date(2026, 11, 4),
    )
    assert FakeCompany.objects.filter(name="Max Muster", vat_number="", company_register_number="").exists()


def test_req_func_070_import_replaces_the_old_list(last_good_copy):
    old_entry, _ = last_good_copy

    sync_bmf(download=serve(SAMPLE))

    assert not FakeCompany.objects.filter(pk=old_entry.pk).exists()
    assert FakeCompany.objects.count() == 2


def test_req_func_072_successful_run_logs_all_fields():
    log = sync_bmf(download=serve(SAMPLE))

    stored = SyncLog.objects.get()
    assert stored == log
    assert stored.source == "BMF"
    assert stored.start_time <= stored.end_time
    assert stored.number_of_entries == 2
    assert stored.feed_timestamp == date(2026, 11, 4)
    assert stored.error_message == ""


def test_req_func_072_one_log_row_per_run():
    sync_bmf(download=serve(SAMPLE))
    sync_bmf(download=fail_with("HTTP_503"))
    sync_bmf(download=serve(SAMPLE))

    assert SyncLog.objects.count() == 3


@pytest.mark.parametrize(
    ("download", "error"),
    [
        (fail_with("HTTP_503"), "HTTP_503"),
        (fail_with("TIMEOUT"), "TIMEOUT"),
        (serve(b"<html>Wartungsarbeiten</html>"), "NOT_RSS"),
        (serve(feed(item("A GmbH", COMPANY.replace("UID-NR", "UID")))), "MARKUP_CHANGED"),
    ],
)
def test_req_func_073_failed_sync_keeps_the_last_good_copy(last_good_copy, download, error):
    old_entry, old_log = last_good_copy

    log = sync_bmf(download=download)

    assert log.outcome == SyncLog.OUTCOME_FAILED
    assert log.error_message.startswith(error)
    assert log.number_of_entries == 0
    assert list(FakeCompany.objects.all()) == [old_entry]
    # The stale flag (SCRUM-66) keeps counting from the last success, not from the failed run.
    assert SyncLog.last_success(SyncLog.SOURCE_BMF) == old_log


def test_req_rel_002_interrupted_write_leaves_the_old_list_complete(last_good_copy, monkeypatch):
    old_entry, old_log = last_good_copy

    def break_halfway(objs, *args, **kwargs):
        list(objs)  # The old list is already deleted inside the transaction at this point.
        raise RuntimeError("connection lost")

    monkeypatch.setattr(FakeCompany.objects, "bulk_create", break_halfway)

    log = sync_bmf(download=serve(SAMPLE))

    assert log.outcome == SyncLog.OUTCOME_FAILED
    assert log.error_message == "RuntimeError: connection lost"
    # The feed was read, so its date is logged even though the run failed.
    assert log.feed_timestamp == date(2026, 11, 4)
    assert list(FakeCompany.objects.all()) == [old_entry]
    assert SyncLog.last_success(SyncLog.SOURCE_BMF) == old_log


def test_much_shorter_list_is_rejected_as_a_broken_download():
    sync_bmf(download=serve(companies(10)))

    log = sync_bmf(download=serve(companies(4)))

    assert log.outcome == SyncLog.OUTCOME_FAILED
    assert log.error_message == "TOO_FEW_ENTRIES: 4 entries, the last good copy has 10"
    assert FakeCompany.objects.count() == 10


def test_shorter_list_is_accepted_when_a_person_allows_it():
    sync_bmf(download=serve(companies(10)))

    log = sync_bmf(download=serve(companies(4)), allow_shrink=True)

    assert log.outcome == SyncLog.OUTCOME_SUCCESS
    assert FakeCompany.objects.count() == 4


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


def test_command_imports_the_feed(monkeypatch, capsys):
    monkeypatch.setattr(bmf_feed.requests, "get", lambda url, timeout: FakeResponse(200, SAMPLE))

    call_command("sync_bmf")

    assert "BMF sync succeeded: 2 entries, feed date 04.11.2026." in capsys.readouterr().out
    assert SyncLog.objects.get().outcome == SyncLog.OUTCOME_SUCCESS


def test_command_fails_so_the_github_run_turns_red(monkeypatch, last_good_copy):
    monkeypatch.setattr(bmf_feed.requests, "get", lambda url, timeout: FakeResponse(503))

    with pytest.raises(CommandError, match="HTTP_503. The last good copy was kept."):
        call_command("sync_bmf")

    assert FakeCompany.objects.count() == 1
