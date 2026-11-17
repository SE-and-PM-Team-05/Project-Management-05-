"""SCRUM-50: HFU adapter tests. The HFU service is mocked."""

import time
from unittest import mock

import pytest
import requests

from checks.results import SOURCE_UNAVAILABLE, UNKNOWN, Partner
from checks.sources.hfu import (
    HfuAdapter,
    HfuUnavailable,
    build_hfu_request,
    parse_hfu_response,
    query_hfu,
)


def fake_hfu_service_response(dg_listed="J", epu_listed="N"):
    """Create a fake HFU SOAP response."""
    response = mock.Mock()
    response.status_code = 200
    response.text = f"""
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
        <soap:Body>
            <ns3:dienstgeberAbfragenResponse
                xmlns:ns3="http://AGHExternWS_3_0.extern_3_0.ws.agh.noegkk.sozvers.at/">
                <auftragnehmerRS>
                    <hfuListeDgJN>{dg_listed}</hfuListeDgJN>
                    <hfuListeEpuJN>{epu_listed}</hfuListeEpuJN>
                </auftragnehmerRS>
            </ns3:dienstgeberAbfragenResponse>
        </soap:Body>
    </soap:Envelope>
    """
    return response


def test_fake_hfu_service_response_contains_listing_fields():
    response = fake_hfu_service_response("J", "N")

    assert response.status_code == 200
    assert "<hfuListeDgJN>J</hfuListeDgJN>" in response.text
    assert "<hfuListeEpuJN>N</hfuListeEpuJN>" in response.text


def test_parse_hfu_response():
    response = fake_hfu_service_response("J", "N")

    result = parse_hfu_response(response.text)

    assert result["dienstgeber"] is True
    assert result["epu"] is False


def test_hfu_listed_as_dienstgeber():
    response = fake_hfu_service_response("J", "N")

    result = parse_hfu_response(response.text)

    assert result["dienstgeber"] is True
    assert result["epu"] is False


def test_hfu_listed_as_epu():
    response = fake_hfu_service_response("N", "J")

    result = parse_hfu_response(response.text)

    assert result["dienstgeber"] is False
    assert result["epu"] is True


def test_build_hfu_request():
    xml = build_hfu_request(
        organization_uid="ATU12345678",
        partner_uid="ATU12345675",
        stichtag="2026-11-16",
    )

    assert "uidAuftraggeber" in xml
    assert "ATU12345678" in xml
    assert "uidAuftragnehmer" in xml
    assert "ATU12345675" in xml
    assert "2026-11-16" in xml
    assert "dienstgeberAbfragen" in xml


def test_query_hfu_uses_mocked_service():
    fake_response = fake_hfu_service_response("J", "N")

    with mock.patch(
        "checks.sources.hfu.requests.post",
        return_value=fake_response,
    ) as mocked_post:
        result = query_hfu(
            organization_uid="ATU12345678",
            partner_uid="ATU12345675",
            stichtag="2026-11-16",
            deadline=time.monotonic() + 10,
        )

    assert result["dienstgeber"] is True
    assert result["epu"] is False

    mocked_post.assert_called_once()


def test_hfu_returns_unknown_without_organization_uid():
    partner = Partner(
        vat_number="ATU12345675",
        company_name="Test Company",
    )

    with mock.patch("checks.sources.hfu.requests.post") as mocked_post:
        result = HfuAdapter().run(
            partner,
            time.monotonic() + 10,
        )

    assert result[0].result == UNKNOWN
    assert result[0].reason == SOURCE_UNAVAILABLE
    mocked_post.assert_not_called()


def test_query_hfu_retries_after_timeout():
    fake_response = fake_hfu_service_response("J", "N")

    with mock.patch(
        "checks.sources.hfu.requests.post",
        side_effect=[
            requests.Timeout(),
            fake_response,
        ],
    ) as mocked_post:
        result = query_hfu(
            organization_uid="ATU12345678",
            partner_uid="ATU12345675",
            stichtag="2026-11-16",
            deadline=time.monotonic() + 10,
        )

    assert result["dienstgeber"] is True
    assert mocked_post.call_count == 2


def test_query_hfu_fails_after_two_timeouts():
    with mock.patch(
        "checks.sources.hfu.requests.post",
        side_effect=[
            requests.Timeout(),
            requests.Timeout(),
        ],
    ) as mocked_post:
        with pytest.raises(HfuUnavailable) as error:
            query_hfu(
                organization_uid="ATU12345678",
                partner_uid="ATU12345675",
                stichtag="2026-11-16",
                deadline=time.monotonic() + 10,
            )

    assert error.value.code == "TIMEOUT"
    assert mocked_post.call_count == 2


def test_query_hfu_retries_after_http_error():
    fake_response = fake_hfu_service_response("J", "N")

    with mock.patch(
        "checks.sources.hfu.requests.post",
        side_effect=[
            mock.Mock(status_code=500),
            fake_response,
        ],
    ) as mocked_post:
        result = query_hfu(
            organization_uid="ATU12345678",
            partner_uid="ATU12345675",
            stichtag="2026-11-16",
            deadline=time.monotonic() + 10,
        )

    assert result["dienstgeber"] is True
    assert mocked_post.call_count == 2


def test_query_hfu_retries_after_invalid_response():
    invalid_response = mock.Mock(
        status_code=200,
        text="<invalid>response</invalid>",
    )

    fake_response = fake_hfu_service_response("J", "N")

    with mock.patch(
        "checks.sources.hfu.requests.post",
        side_effect=[invalid_response, fake_response],
    ) as mocked_post:
        result = query_hfu(
            organization_uid="ATU12345678",
            partner_uid="ATU12345675",
            stichtag="2026-11-16",
            deadline=time.monotonic() + 10,
        )

    assert result["dienstgeber"] is True
    assert mocked_post.call_count == 2


def test_hfu_adapter_returns_unknown_when_service_unavailable():
    partner = Partner(
        vat_number="ATU12345675",
        company_name="Test Company",
        requesting_organization_vat_number="ATU12345678",
    )

    with mock.patch(
        "checks.sources.hfu.query_hfu",
        side_effect=HfuUnavailable("TIMEOUT"),
    ):
        result = HfuAdapter().run(
            partner,
            time.monotonic() + 10,
        )

    assert result[0].result == UNKNOWN
    assert result[0].reason == SOURCE_UNAVAILABLE
    assert result[0].details["error"] == "TIMEOUT"
