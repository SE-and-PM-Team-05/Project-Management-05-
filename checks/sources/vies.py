"""VIES adapter: answers vatValid (REQ-FUNC-031) and nameMatchesVat (REQ-FUNC-032) with one call.

Uses the European Commission's VIES REST API; see docs/sources/vies.md for fields and error cases.
"""

import logging
import time

import requests

from ..names import names_match
from ..results import FALSE, NO_DETAILS_FOUND, SOURCE_UNAVAILABLE, TRUE, UNKNOWN, CheckResult, utc_now
from .base import SourceAdapter

logger = logging.getLogger(__name__)

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
# Placeholders VIES sends instead of a name or address when a member state does not share it.
NO_DATA = {"", "---"}


class ViesUnavailable(Exception):
    """VIES gave no usable answer; `code` is a short, language-neutral reason for the details."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def query_vies(vat_number, deadline):
    """Ask VIES about a normalized VAT number such as "ATU12345678".

    Returns (parsed JSON answer, UTC time of the query that answered), so `dataTimestamp` is the time of
    the query and not of an earlier failed attempt (SRS 3.2.4).

    A transient error (network error, timeout, HTTP 5xx) is retried once if time is left before
    `deadline` (REQ-REL-003). Raises ViesUnavailable when no usable answer arrives in time.
    """
    body = {"countryCode": vat_number[:2], "vatNumber": vat_number[2:]}
    for attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ViesUnavailable("TIMEOUT")
        queried_at = utc_now()
        try:
            response = requests.post(VIES_URL, json=body, timeout=remaining)
        except requests.Timeout:
            error = "TIMEOUT"
        except requests.RequestException:
            error = "NETWORK_ERROR"
        else:
            if response.status_code < 500:
                return _parse(response), queried_at
            error = f"HTTP_{response.status_code}"
        logger.warning("VIES attempt %s failed: %s", attempt, error)
    raise ViesUnavailable(error)


def _parse(response):
    try:
        data = response.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ViesUnavailable("INVALID_RESPONSE" if response.status_code == 200 else f"HTTP_{response.status_code}")
    # VIES reports its own errors (e.g. MS_UNAVAILABLE for a member state that is down) in the body,
    # with HTTP 200 or a 4xx status.
    errors = data.get("errorWrappers") or []
    if errors or data.get("actionSucceed") is False:
        code = errors[0].get("error") if errors and isinstance(errors[0], dict) else None
        raise ViesUnavailable(code or "VIES_ERROR")
    if response.status_code != 200:
        raise ViesUnavailable(f"HTTP_{response.status_code}")
    if data.get("userError") not in (None, "VALID", "INVALID"):
        raise ViesUnavailable(str(data["userError"]))
    # check-vat-number answers with "valid"; accept "isValid" too, which other VIES endpoints use.
    valid = data.get("valid", data.get("isValid"))
    if not isinstance(valid, bool):
        raise ViesUnavailable("INVALID_RESPONSE")
    data["valid"] = valid
    return data


def _text(value):
    """The name or address VIES returned, or None for its "no data" placeholders."""
    if not isinstance(value, str) or value.strip() in NO_DATA:
        return None
    return value.strip()


class ViesAdapter(SourceAdapter):
    source = "VIES"
    checks = ("vatValid", "nameMatchesVat")

    def run(self, partner, deadline):
        try:
            data, queried_at = query_vies(partner.vat_number, deadline)
        except ViesUnavailable as error:
            queried_at = utc_now()
            details = {"error": error.code}
            return [self._unknown(name, SOURCE_UNAVAILABLE, queried_at, details) for name in self.checks]

        registered_name = _text(data.get("name"))
        vat_details = {}
        if data.get("requestIdentifier"):
            vat_details["requestIdentifier"] = data["requestIdentifier"]
        if _text(data.get("address")):
            vat_details["registeredAddress"] = _text(data.get("address"))

        vat_valid = CheckResult(
            "vatValid", TRUE if data["valid"] else FALSE, self.source, queried_at, details=vat_details
        )
        if registered_name is None:
            # Some member states (e.g. Germany) never share the name; invalid numbers have none either.
            name_check = self._unknown("nameMatchesVat", NO_DETAILS_FOUND, queried_at)
        else:
            name_check = CheckResult(
                "nameMatchesVat",
                TRUE if names_match(partner.company_name, registered_name) else FALSE,
                self.source,
                queried_at,
                details={"registeredName": registered_name},
            )
        return [vat_valid, name_check]

    def _unknown(self, check, reason, queried_at, details=None):
        return CheckResult(check, UNKNOWN, self.source, queried_at, reason=reason, details=details or {})
