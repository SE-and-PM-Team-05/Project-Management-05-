"""Download and parse the BMF list of sham companies for the daily sync (REQ-FUNC-070); see docs/sources/bmf.md.

Plain Python without Django, so it can be tested on its own (REQ-MAINT-003). The patterns come from the
SCRUM-18 POC (poc/poc_vies_bmf.py) and also allow tags between a label and its value, so they accept
everything the POC accepted. The parser is strict: whatever it cannot read raises FeedError, so the sync
fails loudly and keeps the last good copy instead of storing a half-read list (REQ-FUNC-073, REQ-REL-002).
"""

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime

import requests

BMF_URL = "https://service.bmf.gv.at/service/allg/lsu/rss_lsu.asp"
# The feed is about 1 MB; the job runs in the background, so it can wait longer than a check would.
TIMEOUT_SECONDS = 60

# Tags that may stand between a label and its value, e.g. "<em>UID-NR:</em> ATU…".
_TAGS = r"\s*(?:<[^>]+>\s*)*"
_VAT = re.compile(r"UID-NR:" + _TAGS + r"(ATU[0-9A-Z\-]+)")
_FN = re.compile(r"Firmenbuch-Nr:" + _TAGS + r"([0-9]+[a-zA-Z])\b")
_ADDRESS = re.compile(r"Anschrift:" + _TAGS + r"<strong>(.*?)</strong>", re.DOTALL)
_DATE_LISTED = re.compile(r"Veröffentlichung:" + _TAGS + r"(\d{2}\.\d{2}\.\d{4})")
# lastBuildDate is a date such as "04 Nov 2026"; a weekday or a time around it is ignored.
_BUILD_DATE = re.compile(r"(\d{1,2}) ([A-Za-z]{3}) (\d{4})")
_MONTHS = {name: number for number, name in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


class FeedError(Exception):
    """The feed could not be downloaded or read; `code` is short and language-neutral, e.g. "HTTP_503"."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class FeedEntry:
    """One listed company or person, with only the fields the check needs (no date of birth, REQ-COMP-001)."""

    name: str
    vat_number: str
    company_register_number: str
    address: str
    date_listed: date


@dataclass(frozen=True)
class Feed:
    build_date: date
    entries: list[FeedEntry]


def download(url=BMF_URL, timeout=TIMEOUT_SECONDS):
    """Return the raw feed as bytes; the XML header declares its encoding (iso-8859-1)."""
    try:
        response = requests.get(url, timeout=timeout)
    except requests.Timeout as error:
        raise FeedError("TIMEOUT") from error
    except requests.RequestException as error:
        raise FeedError("NETWORK_ERROR", str(error)) from error
    if response.status_code != 200:
        raise FeedError(f"HTTP_{response.status_code}")
    return response.content


def parse(xml_bytes):
    """Read the whole feed into a Feed, or raise FeedError if any part of it does not look as expected."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        raise FeedError("INVALID_XML", str(error)) from error
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedError("NOT_RSS")
    entries = [_parse_item(item, number) for number, item in enumerate(channel.iter("item"), 1)]
    if not entries:
        raise FeedError("EMPTY_FEED")
    # 83 % of the entries have a VAT number and 63 % an FN (docs/sources/bmf.md). If none has one, BMF has
    # changed its markup and the matching keys would silently be lost.
    if not any(entry.vat_number for entry in entries):
        raise FeedError("MARKUP_CHANGED", "no entry has a VAT number")
    if not any(entry.company_register_number for entry in entries):
        raise FeedError("MARKUP_CHANGED", "no entry has a Firmenbuch number")
    return Feed(_parse_build_date(channel.findtext("lastBuildDate")), entries)


def _parse_item(item, number):
    name = _clean(item.findtext("title"))
    if not name:
        raise FeedError("MISSING_NAME", f"item {number}")
    description = item.findtext("description") or ""
    date_listed = _DATE_LISTED.search(description)
    if not date_listed:
        raise FeedError("MISSING_DATE_LISTED", f"item {number} ({name})")
    try:
        listed = datetime.strptime(date_listed.group(1), "%d.%m.%Y").date()
    except ValueError as error:
        raise FeedError("BAD_DATE_LISTED", f"item {number} ({name}): {date_listed.group(1)}") from error
    vat = _VAT.search(description)
    fn = _FN.search(description)
    address = _ADDRESS.search(description)
    return FeedEntry(
        name=name,
        # A suffix such as "-B" is dropped, as in the POC.
        vat_number=vat.group(1).split("-")[0] if vat else "",
        # Stored as the check compares it: lowercase, no spaces (checks/sources/bmf.py).
        company_register_number=fn.group(1).lower() if fn else "",
        address=_clean(address.group(1)) if address else "",
        date_listed=listed,
    )


def _parse_build_date(text):
    """The feed's own timestamp for the sync log (REQ-FUNC-072); it is required, so a missing one fails."""
    found = _BUILD_DATE.search(text or "")
    month = _MONTHS.get(found.group(2).lower()) if found else None
    if not month:
        raise FeedError("BAD_BUILD_DATE", repr(text))
    try:
        return date(int(found.group(3)), month, int(found.group(1)))
    except ValueError as error:
        raise FeedError("BAD_BUILD_DATE", repr(text)) from error


def _clean(text):
    """Plain text from an HTML fragment: tags become spaces, entities are decoded, spaces collapsed."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(html.unescape(text).split())
