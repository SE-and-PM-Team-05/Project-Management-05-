"""HFU adapter for checking whether a business is on the HFU list."""

import logging
import time
import xml.etree.ElementTree as ET

import requests

from ..results import (
    SOURCE_UNAVAILABLE,
    UNKNOWN,
    CheckResult,
    utc_now,
)
from .base import SourceAdapter

logger = logging.getLogger(__name__)

HFU_URL = "https://www.sozialversicherung.at/agh-ws-prod/DienstgeberAbfrageWS_3_0"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
AGH_NS = "http://AGHExternWS_3_0.extern_3_0.ws.agh.noegkk.sozvers.at/"


class HfuUnavailable(Exception):
    """HFU gave no usable answer."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def build_hfu_request(organization_uid, partner_uid, stichtag):
    """Build the XML request for the HFU SOAP service."""

    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")

    request = ET.SubElement(body, f"{{{AGH_NS}}}dienstgeberAbfragen")

    ET.SubElement(request, f"{{{AGH_NS}}}uidAuftraggeber").text = organization_uid
    ET.SubElement(request, f"{{{AGH_NS}}}stichtag").text = stichtag

    partner_request = ET.SubElement(request, f"{{{AGH_NS}}}auftragnehmerRQ")

    ET.SubElement(partner_request, f"{{{AGH_NS}}}uidAuftragnehmer").text = partner_uid

    return ET.tostring(envelope, encoding="unicode")


def query_hfu(organization_uid, partner_uid, stichtag, deadline):
    """Send a SOAP request to HFU and retry temporary errors once."""

    soap_xml = build_hfu_request(
        organization_uid,
        partner_uid,
        stichtag,
    )

    error = "UNKNOWN_ERROR"

    for attempt in (1, 2):
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise HfuUnavailable("TIMEOUT")

        try:
            response = requests.post(
                HFU_URL,
                data=soap_xml.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=remaining,
            )

        except requests.Timeout:
            error = "TIMEOUT"

        except requests.RequestException:
            error = "NETWORK_ERROR"

        else:
            if response.status_code == 200:
                try:
                    return parse_hfu_response(response.text)
                except ValueError, ET.ParseError:
                    error = "INVALID_RESPONSE"
            else:
                error = f"HTTP_{response.status_code}"
        logger.warning("HFU attempt %s failed: %s", attempt, error)
    raise HfuUnavailable(error)


def parse_hfu_response(xml_text):
    """Read the listing information from an HFU SOAP response."""

    root = ET.fromstring(xml_text)

    dg_listed = root.find(".//hfuListeDgJN")
    epu_listed = root.find(".//hfuListeEpuJN")

    if dg_listed is None or epu_listed is None:
        raise ValueError("HFU listing information is missing")

    return {
        "dienstgeber": dg_listed.text == "J",
        "epu": epu_listed.text == "J",
    }


class HfuAdapter(SourceAdapter):
    source = "OEGK"
    checks = ("onHfuList",)

    def run(self, partner, deadline):
        if not partner.requesting_organization_vat_number:
            return [
                CheckResult(
                    check="onHfuList",
                    result=UNKNOWN,
                    source=self.source,
                    data_timestamp=utc_now(),
                    reason=SOURCE_UNAVAILABLE,
                    details={"error": "MISSING_ORGANIZATION_UID"},
                )
            ]

        try:
            query_hfu(
                organization_uid=partner.requesting_organization_vat_number,
                partner_uid=partner.vat_number,
                stichtag=utc_now().date().isoformat(),
                deadline=deadline,
            )

        except HfuUnavailable as error:
            return [
                CheckResult(
                    check="onHfuList",
                    result=UNKNOWN,
                    source=self.source,
                    data_timestamp=utc_now(),
                    reason=SOURCE_UNAVAILABLE,
                    details={"error": error.code},
                )
            ]

        # The mapping of the two HFU flags to onHfuList
        # still needs confirmation.
        return [
            CheckResult(
                check="onHfuList",
                result=UNKNOWN,
                source=self.source,
                data_timestamp=utc_now(),
                details={"error": "HFU_RESULT_MAPPING_PENDING"},
            )
        ]
