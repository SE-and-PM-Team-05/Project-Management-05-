"""HFU adapter: is the partner on the ÖGK HFU list? (REQ-FUNC-034, REQ-FUNC-071)

The HFU web service (SOAP, version 3.0) is asked live for every check, by VAT number only. The request and
response format follow the service's WSDL (DienstgeberAbfrageWS_3_0?wsdl): only the top-level elements
are in the service namespace; their children (uidAuftraggeber, hfuListeDgJN, ...) have no namespace.
"""

import logging
import time
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests

from ..results import FALSE, SOURCE_UNAVAILABLE, TRUE, utc_now
from .base import SourceAdapter

logger = logging.getLogger(__name__)

HFU_URL = "https://www.sozialversicherung.at/agh-ws-prod/DienstgeberAbfrageWS_3_0"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
AGH_NS = "http://AGHExternWS_3_0.extern_3_0.ws.agh.noegkk.sozvers.at/"
# The WSDL declares soapAction="", and SOAP 1.1 expects the header to be present.
HEADERS = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}
# The list is Austrian, so "today" is the day in Vienna, not in UTC.
VIENNA = ZoneInfo("Europe/Vienna")


class HfuUnavailable(Exception):
    """HFU gave no usable answer."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def build_hfu_request(organization_uid, partner_uid, stichtag):
    """Build the SOAP request: who asks (uidAuftraggeber), about whom (uidAuftragnehmer) and for which day."""
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    request = ET.SubElement(body, f"{{{AGH_NS}}}dienstgeberAbfragen")
    ET.SubElement(request, "uidAuftraggeber").text = organization_uid
    ET.SubElement(request, "stichtag").text = stichtag
    partner_request = ET.SubElement(request, "auftragnehmerRQ")
    ET.SubElement(partner_request, "uidAuftragnehmer").text = partner_uid
    return ET.tostring(envelope, encoding="unicode")


def query_hfu(organization_uid, partner_uid, stichtag, deadline):
    """Ask the HFU service; retry once on network errors and server errors (REQ-REL-003)."""
    soap_xml = build_hfu_request(organization_uid, partner_uid, stichtag).encode("utf-8")
    error = "UNKNOWN_ERROR"

    for attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HfuUnavailable("TIMEOUT")
        try:
            response = requests.post(HFU_URL, data=soap_xml, headers=HEADERS, timeout=remaining)
        except requests.Timeout:
            error = "TIMEOUT"
        except requests.RequestException:
            error = "NETWORK_ERROR"
        else:
            if response.status_code == 200:
                try:
                    return parse_hfu_response(response.content)
                except ValueError, ET.ParseError:
                    error = "INVALID_RESPONSE"
            elif is_soap_fault(response.content):
                # The service rejected the request itself; asking again gives the same answer.
                logger.warning("HFU returned a SOAP fault (HTTP %s)", response.status_code)
                raise HfuUnavailable("SOAP_FAULT")
            elif response.status_code < 500:
                # 4xx: our request is wrong, a retry will not help.
                raise HfuUnavailable(f"HTTP_{response.status_code}")
            else:
                error = f"HTTP_{response.status_code}"
        logger.warning("HFU attempt %s failed: %s", attempt, error)
    raise HfuUnavailable(error)


def is_soap_fault(content):
    try:
        return ET.fromstring(content).find(f".//{{{SOAP_NS}}}Fault") is not None
    except ET.ParseError:
        return False


def parse_hfu_response(content):
    """Read both HFU flags from the response; anything other than J or N is an invalid answer."""
    root = ET.fromstring(content)
    return {
        "dienstgeber": _flag(root, "hfuListeDgJN"),
        "epu": _flag(root, "hfuListeEpuJN"),
    }


def _flag(root, name):
    element = root.find(f".//{name}")
    value = (element.text or "").strip() if element is not None else None
    if value not in ("J", "N"):
        raise ValueError(f"{name} is {value!r}, expected J or N")
    return value == "J"


class HfuAdapter(SourceAdapter):
    """onHfuList (REQ-FUNC-034): informational; FALSE is normal and means part of the payment is withheld."""

    source = "OEGK"
    checks = ("onHfuList",)

    def applies_to(self, partner):
        # The service is queried by VAT number only, so only Austrian VAT numbers can be checked (REQ-FUNC-038).
        return partner.vat_number.startswith("ATU")

    def run(self, partner, deadline):
        queried_at = utc_now()
        stichtag = queried_at.astimezone(VIENNA).date().isoformat()

        if not partner.requesting_organization_vat_number:
            return [self.unavailable_with_stichtag(queried_at, stichtag, "MISSING_ORGANIZATION_UID")]
        try:
            listing = query_hfu(
                organization_uid=partner.requesting_organization_vat_number,
                partner_uid=partner.vat_number,
                stichtag=stichtag,
                deadline=deadline,
            )
        except HfuUnavailable as error:
            return [self.unavailable_with_stichtag(queried_at, stichtag, error.code)]

        # Listed on either HFU list (employer or one-person company) means no withholding.
        listed = listing["dienstgeber"] or listing["epu"]
        return [
            self.result(
                "onHfuList",
                TRUE if listed else FALSE,
                queried_at,
                details={"stichtag": stichtag, "withholdingApplies": not listed},
            )
        ]

    def unavailable_with_stichtag(self, queried_at, stichtag, error):
        """UNKNOWN / SOURCE_UNAVAILABLE that still shows which day was asked about (SCRUM-50)."""
        return self.unknown("onHfuList", SOURCE_UNAVAILABLE, queried_at, {"stichtag": stichtag, "error": error})
