"""VIES adapter: answers vatValid (REQ-FUNC-031) and nameMatchesVat (REQ-FUNC-032) with one call.

Uses the European Commission's VIES REST API; see docs/sources/vies.md for fields and error cases.
"""

import logging

from ..names import names_match
from ..results import FALSE, NO_DETAILS_FOUND, NOT_APPLICABLE, TRUE
from .base import SourceAdapter
from .http import SourceUnavailable, post_within_budget

logger = logging.getLogger(__name__)

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
# Placeholders VIES sends instead of a name or address when a member state does not share it.
NO_DATA = {"", "---"}


# Kept as a name of its own so the VIES code reads clearly; it is the shared SourceUnavailable.
ViesUnavailable = SourceUnavailable


# VIES error for a requester VAT number it does not accept.
INVALID_REQUESTER = "INVALID_REQUESTER_INFO"


def query_vies(vat_number, deadline, requester_vat_number=""):
    """Ask VIES about a normalized VAT number such as "ATU12345678".

    With `requester_vat_number` (the checking organization's own VAT number), VIES returns a
    `requestIdentifier`, its consultation number, which is stored as evidence (REQ-FUNC-050). If VIES rejects
    the requester, the query is repeated once without it, so the check itself still runs.

    Returns (parsed JSON answer, UTC time of the query that answered), so `dataTimestamp` is the time of
    the query and not of an earlier failed attempt (SRS 3.2.4). Transient errors are retried once within
    the budget (see post_within_budget). Raises ViesUnavailable when no usable answer arrives in time.
    """
    body = {"countryCode": vat_number[:2], "vatNumber": vat_number[2:]}
    if requester_vat_number:
        requester = {
            **body,
            "requesterMemberStateCode": requester_vat_number[:2],
            "requesterNumber": requester_vat_number[2:],
        }
        try:
            response, queried_at = post_within_budget(VIES_URL, deadline, source="VIES", json=requester)
            return _parse(response), queried_at
        except ViesUnavailable as error:
            if error.code != INVALID_REQUESTER:
                raise
            logger.warning("VIES rejected the requester VAT number; asking again without it")
    response, queried_at = post_within_budget(VIES_URL, deadline, source="VIES", json=body)
    return _parse(response), queried_at


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
            data, queried_at = query_vies(partner.vat_number, deadline, partner.requesting_organization_vat_number)
        except ViesUnavailable as error:
            vat_valid, name_check = self.unavailable(error.code)
            if not partner.company_name:
                # Nothing to compare without a name, whether or not VIES answered (REQ-FUNC-032).
                name_check = self.result("nameMatchesVat", NOT_APPLICABLE, None)
            return [vat_valid, name_check]

        registered_name = _text(data.get("name"))
        vat_details = {}
        if data.get("requestIdentifier"):
            vat_details["requestIdentifier"] = data["requestIdentifier"]
        if _text(data.get("address")):
            vat_details["registeredAddress"] = _text(data.get("address"))

        vat_valid = self.result("vatValid", TRUE if data["valid"] else FALSE, queried_at, details=vat_details)
        if not partner.company_name:
            # No name given (REQ-FUNC-032): nothing to compare, but the registered name is still reported.
            details = {"registeredName": registered_name} if registered_name else {}
            name_check = self.result("nameMatchesVat", NOT_APPLICABLE, queried_at, details=details)
        elif registered_name is None:
            # Some member states (e.g. Germany) never share the name; invalid numbers have none either.
            name_check = self.unknown("nameMatchesVat", NO_DETAILS_FOUND, queried_at)
        else:
            name_check = self.result(
                "nameMatchesVat",
                TRUE if names_match(partner.company_name, registered_name) else FALSE,
                queried_at,
                details={"registeredName": registered_name},
            )
        return [vat_valid, name_check]
