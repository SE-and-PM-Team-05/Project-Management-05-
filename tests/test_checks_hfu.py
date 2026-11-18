"""SCRUM-50: HFU adapter (REQ-FUNC-034, REQ-FUNC-071). The HFU service is always mocked.

The fixtures follow the service's WSDL (DienstgeberAbfrageWS_3_0?wsdl): the response element is in the
service namespace, its children have no namespace. No real response has been recorded yet.
"""

import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from unittest import mock

import pytest
import requests

from checks.results import FALSE, NOT_APPLICABLE, SOURCE_UNAVAILABLE, TRUE, UNKNOWN, Partner
from checks.runner import run_checks
from checks.sources.hfu import (
    AGH_NS,
    HFU_URL,
    SOAP_NS,
    HfuAdapter,
    HfuUnavailable,
    build_hfu_request,
    parse_hfu_response,
    query_hfu,
)

PARTNER = Partner(
    vat_number="ATU12345675",
    company_name="Test Company",
    requesting_organization_vat_number="ATU12345678",
)


def soap_response(dg="N", epu="N", status=200):
    """An HFU answer in the shape of the WSDL's dtoAuftragnehmerRsDetail."""
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
    <soap:Envelope xmlns:soap="{SOAP_NS}">
      <soap:Body>
        <ns2:dienstgeberAbfragenResponse xmlns:ns2="{AGH_NS}">
          <auftragnehmerRS>
            <auftragnehmerName>Test Company GmbH</auftragnehmerName>
            <uid>ATU12345675</uid>
            <hfuListeDgJN>{dg}</hfuListeDgJN>
            <hfuListeEpuJN>{epu}</hfuListeEpuJN>
          </auftragnehmerRS>
        </ns2:dienstgeberAbfragenResponse>
      </soap:Body>
    </soap:Envelope>"""
    return mock.Mock(status_code=status, content=body.encode("utf-8"))


def soap_fault(status=500):
    body = f"""<soap:Envelope xmlns:soap="{SOAP_NS}"><soap:Body><soap:Fault>
      <faultcode>soap:Client</faultcode><faultstring>Ungültige UID</faultstring>
    </soap:Fault></soap:Body></soap:Envelope>"""
    return mock.Mock(status_code=status, content=body.encode("utf-8"))


def query(side_effect, deadline=None):
    with mock.patch("checks.sources.hfu.requests.post", side_effect=side_effect) as post:
        result = query_hfu("ATU12345678", "ATU12345675", "2026-11-16", deadline or time.monotonic() + 10)
    return result, post


def query_fails(side_effect):
    with mock.patch("checks.sources.hfu.requests.post", side_effect=side_effect) as post:
        with pytest.raises(HfuUnavailable) as error:
            query_hfu("ATU12345678", "ATU12345675", "2026-11-16", time.monotonic() + 10)
    return error.value.code, post


# --- Request ---


def test_request_follows_the_wsdl():
    """Verifies REQ-FUNC-034."""
    root = ET.fromstring(build_hfu_request("ATU12345678", "ATU12345675", "2026-11-16"))
    request = root.find(f"{{{SOAP_NS}}}Body/{{{AGH_NS}}}dienstgeberAbfragen")

    assert request is not None
    # Child elements have no namespace (the schema has no elementFormDefault="qualified").
    assert request.findtext("uidAuftraggeber") == "ATU12345678"
    assert request.findtext("stichtag") == "2026-11-16"
    assert request.findtext("auftragnehmerRQ/uidAuftragnehmer") == "ATU12345675"


def test_query_posts_the_request_to_the_service():
    """Verifies REQ-FUNC-034, REQ-FUNC-071."""
    result, post = query([soap_response(dg="J")])

    assert result == {"dienstgeber": True, "epu": False}
    post.assert_called_once()
    assert post.call_args.args[0] == HFU_URL
    headers = post.call_args.kwargs["headers"]
    assert headers["Content-Type"] == "text/xml; charset=utf-8"
    assert headers["SOAPAction"] == '""'
    assert b"<uidAuftraggeber>ATU12345678</uidAuftraggeber>" in post.call_args.kwargs["data"]
    assert b"<uidAuftragnehmer>ATU12345675</uidAuftragnehmer>" in post.call_args.kwargs["data"]


# --- Parsing ---


@pytest.mark.parametrize(
    ("dg", "epu", "expected"),
    [
        ("J", "N", {"dienstgeber": True, "epu": False}),
        ("N", "J", {"dienstgeber": False, "epu": True}),
        ("N", "N", {"dienstgeber": False, "epu": False}),
        (" J\n", "N", {"dienstgeber": True, "epu": False}),
    ],
)
def test_parse_reads_both_flags(dg, epu, expected):
    """Verifies REQ-FUNC-034."""
    assert parse_hfu_response(soap_response(dg, epu).content) == expected


@pytest.mark.parametrize("value", ["", "X", "ja", "Fehler bei der Abfrage"])
def test_parse_rejects_anything_but_j_or_n(value):
    # Otherwise an empty or unexpected value would be stored as FALSE, an answer ÖGK never gave.
    """Verifies REQ-FUNC-034, REQ-REL-001."""
    with pytest.raises(ValueError):
        parse_hfu_response(soap_response(dg=value).content)


def test_parse_rejects_a_missing_flag():
    """Verifies REQ-FUNC-034, REQ-REL-001."""
    content = soap_response().content.replace(b"<hfuListeEpuJN>N</hfuListeEpuJN>", b"")
    with pytest.raises(ValueError):
        parse_hfu_response(content)


# --- Errors and retries (REQ-REL-003) ---


def test_retries_once_after_a_timeout():
    """Verifies REQ-REL-003."""
    result, post = query([requests.Timeout(), soap_response(dg="J")])

    assert result["dienstgeber"] is True
    assert post.call_count == 2


def test_two_timeouts_end_as_timeout():
    """Verifies REQ-REL-003, REQ-INT-013."""
    code, post = query_fails([requests.Timeout(), requests.Timeout()])

    assert code == "TIMEOUT"
    assert post.call_count == 2


def test_retries_once_after_a_server_error():
    """Verifies REQ-REL-003."""
    result, post = query([mock.Mock(status_code=503, content=b"busy"), soap_response(dg="J")])

    assert result["dienstgeber"] is True
    assert post.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_not_retried(status):
    """Verifies REQ-REL-003."""
    code, post = query_fails([mock.Mock(status_code=status, content=b"")])

    assert code == f"HTTP_{status}"
    assert post.call_count == 1


def test_soap_fault_is_not_retried():
    """Verifies REQ-REL-003."""
    code, post = query_fails([soap_fault()])

    assert code == "SOAP_FAULT"
    assert post.call_count == 1


def test_retries_once_after_an_invalid_response():
    """Verifies REQ-REL-003."""
    invalid = mock.Mock(status_code=200, content=b"<invalid>response</invalid>")
    result, post = query([invalid, soap_response(dg="J")])

    assert result["dienstgeber"] is True
    assert post.call_count == 2


def test_malformed_xml_twice_ends_as_invalid_response():
    """Verifies REQ-REL-003, REQ-REL-001."""
    code, post = query_fails([mock.Mock(status_code=200, content=b"<not xml")] * 2)

    assert code == "INVALID_RESPONSE"
    assert post.call_count == 2


def test_no_request_when_the_deadline_is_used_up():
    """Verifies REQ-INT-013."""
    with mock.patch("checks.sources.hfu.requests.post") as post:
        with pytest.raises(HfuUnavailable) as error:
            query_hfu("ATU12345678", "ATU12345675", "2026-11-16", time.monotonic() - 1)

    assert error.value.code == "TIMEOUT"
    post.assert_not_called()


# --- Adapter ---

# 23:30 UTC on 16 November is already 17 November in Vienna.
LATE_EVENING_UTC = datetime(2026, 11, 16, 23, 30, tzinfo=UTC)


def run_adapter(partner=PARTNER, **query_mock):
    with (
        mock.patch("checks.sources.hfu.utc_now", return_value=LATE_EVENING_UTC),
        mock.patch("checks.sources.hfu.query_hfu", **query_mock) as query_hfu_mock,
    ):
        [result] = HfuAdapter().run(partner, time.monotonic() + 10)
    return result, query_hfu_mock


@pytest.mark.parametrize(
    ("listing", "expected"),
    [
        ({"dienstgeber": True, "epu": False}, TRUE),
        ({"dienstgeber": False, "epu": True}, TRUE),
        ({"dienstgeber": False, "epu": False}, FALSE),
    ],
)
def test_req_func_034_listing_maps_to_true_or_false(listing, expected):
    """Verifies REQ-FUNC-034."""
    result, _ = run_adapter(return_value=listing)

    assert result.check == "onHfuList"
    assert result.source == "OEGK"
    assert result.result == expected
    assert result.reason is None
    assert result.details == {"stichtag": "2026-11-17", "withholdingApplies": expected == FALSE}


def test_stichtag_is_the_vienna_date_and_matches_the_data_timestamp():
    """Verifies REQ-FUNC-034."""
    result, query_hfu_mock = run_adapter(return_value={"dienstgeber": False, "epu": False})

    assert query_hfu_mock.call_args.kwargs["stichtag"] == "2026-11-17"
    assert result.data_timestamp == LATE_EVENING_UTC


def test_req_func_034_unavailable_result_includes_stichtag():
    """Verifies REQ-FUNC-034."""
    result, _ = run_adapter(side_effect=HfuUnavailable("HTTP_503"))

    assert result.result == UNKNOWN
    assert result.reason == SOURCE_UNAVAILABLE
    assert result.data_timestamp == LATE_EVENING_UTC
    assert result.details == {"stichtag": "2026-11-17", "error": "HTTP_503"}


def test_unknown_without_organization_uid_and_no_query():
    """Verifies REQ-FUNC-034."""
    result, query_hfu_mock = run_adapter(Partner(vat_number="ATU12345675", company_name="Test Company"))

    assert result.result == UNKNOWN
    assert result.details["error"] == "MISSING_ORGANIZATION_UID"
    query_hfu_mock.assert_not_called()


@pytest.mark.parametrize(
    ("vat_number", "applies"),
    [("ATU12345675", True), ("DE123456789", False), ("CZ12345678", False)],
)
def test_req_func_038_only_austrian_vat_numbers_are_checked(vat_number, applies):
    """Verifies REQ-FUNC-038."""
    assert HfuAdapter().applies_to(Partner(vat_number=vat_number, company_name="X")) is applies


def test_req_func_038_other_partners_get_not_applicable():
    """Verifies REQ-FUNC-038."""
    partner = Partner(vat_number="DE123456789", company_name="X", requesting_organization_vat_number="ATU1")

    with mock.patch("checks.sources.hfu.query_hfu") as query_hfu_mock:
        [result] = run_checks(partner, adapters=[HfuAdapter()])

    assert result.result == NOT_APPLICABLE
    query_hfu_mock.assert_not_called()
