"""SCRUM-64: reading the BMF feed for the daily sync (REQ-FUNC-070). No database or network needed."""

from datetime import date

import pytest
import requests

from checks.sources import bmf_feed
from checks.sources.bmf_feed import FeedError

from .bmf_samples import COMPANY, SAMPLE, feed, item


def test_reads_every_entry_with_the_fields_the_check_needs():
    result = bmf_feed.parse(SAMPLE)

    assert result.build_date == date(2026, 11, 4)
    assert result.entries == [
        bmf_feed.FeedEntry(
            name="Schein Bau & Co GmbH",
            vat_number="ATU12345678",
            company_register_number="123456a",
            address="Hauptstraße 1, 1010 Wien",
            date_listed=date(2026, 11, 4),
        ),
        bmf_feed.FeedEntry(
            name="Max Muster",
            vat_number="",
            company_register_number="",
            address="Gasse 2/3, 8010 Graz",
            date_listed=date(2026, 10, 15),
        ),
    ]


def test_req_comp_001_date_of_birth_is_not_kept():
    person = bmf_feed.parse(SAMPLE).entries[1]

    assert "1980" not in repr(person)


def test_accepts_the_markup_the_poc_parsed():
    # The POC's patterns, e.g. "Firmenbuch-Nr: 123456a" and "UID-NR:</em> ATU…", without extra tags.
    description = (
        "Anschrift: <strong>Ring 5, 4020 Linz</strong> <em>Veröffentlichung:</em> 01.09.2026, "
        "Firmenbuch-Nr: 654321B <em>UID-NR:</em> ATU87654321"
    )

    entry = bmf_feed.parse(feed(item("Linz Bau GmbH", description))).entries[0]

    assert (entry.vat_number, entry.company_register_number, entry.address) == (
        "ATU87654321",
        "654321b",
        "Ring 5, 4020 Linz",
    )


@pytest.mark.parametrize("build_date", ["Wed, 04 Nov 2026", "04 Nov 2026 00:00:00 GMT", "4 nov 2026"])
def test_build_date_ignores_weekday_time_and_case(build_date):
    assert bmf_feed.parse(feed(item("A GmbH", COMPANY), build_date=build_date)).build_date == date(2026, 11, 4)


@pytest.mark.parametrize(
    ("xml_bytes", "code"),
    [
        (b"<html>Wartungsarbeiten</html>", "NOT_RSS"),
        (b"<rss><channel>", "INVALID_XML"),
        (feed(), "EMPTY_FEED"),
        (feed(item("", COMPANY)), "MISSING_NAME"),
        (feed(item("A GmbH", COMPANY.replace("Veröffentlichung", "Publiziert"))), "MISSING_DATE_LISTED"),
        (feed(item("A GmbH", COMPANY.replace("04.11.2026", "31.02.2026"))), "BAD_DATE_LISTED"),
        (feed(item("A GmbH", COMPANY), build_date=None), "BAD_BUILD_DATE"),
        (feed(item("A GmbH", COMPANY), build_date="gestern"), "BAD_BUILD_DATE"),
        # A changed label would silently drop a matching key from every entry.
        (feed(item("A GmbH", COMPANY.replace("UID-NR", "UID"))), "MARKUP_CHANGED"),
        (feed(item("A GmbH", COMPANY.replace("Firmenbuch-Nr", "FN"))), "MARKUP_CHANGED"),
    ],
)
def test_req_func_073_anything_unreadable_fails_loudly(xml_bytes, code):
    with pytest.raises(FeedError) as raised:
        bmf_feed.parse(xml_bytes)

    assert raised.value.code == code


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


def test_download_returns_the_raw_feed(monkeypatch):
    monkeypatch.setattr(bmf_feed.requests, "get", lambda url, timeout: FakeResponse(200, SAMPLE))

    assert bmf_feed.download() == SAMPLE


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (FakeResponse(503), "HTTP_503"),
        (requests.Timeout(), "TIMEOUT"),
        (requests.ConnectionError("refused"), "NETWORK_ERROR"),
    ],
)
def test_download_errors_have_a_short_code(monkeypatch, outcome, code):
    def get(url, timeout):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(bmf_feed.requests, "get", get)

    with pytest.raises(FeedError) as raised:
        bmf_feed.download()

    assert raised.value.code == code
