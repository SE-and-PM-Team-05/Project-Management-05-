"""BMF adapter: answers listedAsFakeCompany (REQ-FUNC-033) from the locally synced list of sham companies.

Unlike the other adapters this one reads the database, because the list is synced daily (REQ-FUNC-070)
and not queried live. It sets `stale` when the last successful sync is older than 48 h (REQ-FUNC-073).
"""

import threading
from datetime import timedelta

from ..names import normalize_company_name
from ..results import AMBIGUOUS_MATCH, FALSE, TRUE, UNKNOWN, CheckResult, utc_now
from .base import SourceAdapter

STALE_AFTER = timedelta(hours=48)
CHECK = "listedAsFakeCompany"


def is_austrian(partner):
    """REQ-FUNC-038: the list covers Austrian companies; an FN also marks one."""
    return partner.vat_number.startswith("ATU") or bool(partner.company_register_number)


def entry_details(entry, matched_by):
    details = {
        "name": entry.name,
        "vatNumber": entry.vat_number,
        "companyRegisterNumber": entry.company_register_number,
        "address": entry.address,
        "dateListed": entry.date_listed.isoformat(),
    }
    details = {key: value for key, value in details.items() if value}
    details["matchedBy"] = matched_by
    return details


def normalize_fn(fn):
    """The FN as the API input stores it (checks/forms.py): no spaces, lowercase, no "FN" prefix."""
    return fn.replace(" ", "").lower().removeprefix("fn")


def find_match(partner, entries):
    """Return (result, details) for a partner against list entries (VAT, then FN, then name if one was given)."""
    for entry in entries:
        if entry.vat_number == partner.vat_number:
            return TRUE, entry_details(entry, "vatNumber")
    fn = normalize_fn(partner.company_register_number)
    if fn:
        for entry in entries:
            if normalize_fn(entry.company_register_number) == fn:
                return TRUE, entry_details(entry, "companyRegisterNumber")
    name = normalize_company_name(partner.company_name)
    if not name:
        # No name given (SCRUM-93): VAT number and FN were the only keys.
        return FALSE, {}
    # A name alone is no proof, so it only gives UNKNOWN / AMBIGUOUS_MATCH for a person to review.
    candidates = [entry_details(e, "name") for e in entries if normalize_company_name(e.name) == name]
    if candidates:
        return UNKNOWN, {"candidates": candidates}
    return FALSE, {}


class BmfAdapter(SourceAdapter):
    source = "BMF"
    checks = (CHECK,)

    def applies_to(self, partner):
        return is_austrian(partner)

    def run(self, partner, deadline):
        # Imported here so the registry can load before Django's apps are ready.
        from django.db import connection

        from ..models import FakeCompany, SyncLog

        try:
            last_success = SyncLog.last_success(SyncLog.SOURCE_BMF)
            if last_success is None:
                return self.unavailable("NO_SYNC")
            # ponytail: ~1,700 rows scanned in Python; store a normalized name column if the list grows a lot.
            entries = list(
                FakeCompany.objects.only(
                    "id", "name", "vat_number", "company_register_number", "address", "date_listed"
                )
            )
            result, details = find_match(partner, entries)
            reason = AMBIGUOUS_MATCH if result == UNKNOWN else None
            stale = utc_now() - last_success.end_time > STALE_AFTER
            return [
                CheckResult(
                    CHECK,
                    result,
                    self.source,
                    data_timestamp=last_success.end_time,
                    reason=reason,
                    details=details,
                    stale=stale,
                )
            ]
        finally:
            # Django does not close connections opened in threads it doesn't manage; the main thread keeps its own.
            if threading.current_thread() is not threading.main_thread():
                connection.close()
