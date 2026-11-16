# Source: VIES (EU VAT Information Exchange System)

Integration note required by REQ-INT-016. Code: `checks/sources/vies.py`, name rules: `checks/names.py`.

| | |
|---|---|
| **Owner** | European Commission, DG TAXUD (SRS reference R5) |
| **Checks** | `vatValid` (REQ-FUNC-031), `nameMatchesVat` (REQ-FUNC-032) – both from one call |
| **Applies to** | Every EU VAT number (all member states plus `XI` for Northern Ireland; Greece is `EL`) |
| **Access** | Live HTTPS call, free, no account or key |
| **Endpoint** | `POST https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number` |
| **Freshness** | Live; `dataTimestamp` is the time BizPartnerCheck sent the query that answered (UTC) |

## Request

```json
{ "countryCode": "AT", "vatNumber": "U12345678" }
```

VIES wants the country code and the rest of the number separately. BizPartnerCheck normalizes the input
first (`atu 123 456 78` → `ATU12345678`) and splits after the second character.

## Response fields used

| Field | Used for |
|---|---|
| `valid` (boolean; `isValid` is accepted too) | `vatValid` TRUE / FALSE |
| `name` | `nameMatchesVat`; reported as `details.registeredName` |
| `address` | Reported as `vatValid.details.registeredAddress` |
| `requestIdentifier` | Reported as `vatValid.details.requestIdentifier` when not empty (only filled if a requester VAT number is sent, which we don't do yet) |
| `actionSucceed`, `errorWrappers[].error`, `userError` | Error detection (see below) |

Some member states (e.g. Germany) never share name or address; VIES then sends `---` or nothing.
BizPartnerCheck treats `---`, an empty string and a missing field the same: `nameMatchesVat` becomes
`UNKNOWN / NO_DETAILS_FOUND`. An invalid number has no name either, so the same applies there.

## Name matching (REQ-FUNC-032, SRS 3.6)

Deterministic, no fuzzy logic. Both names are lower-cased, dots are dropped, other punctuation becomes a
space, one legal-form suffix (GmbH, AG, KG, OG, e.U., GmbH & Co KG, Ltd, SE, …) is removed from the end,
and the results must be identical. The full list and rules are in `checks/names.py`. Not handled on
purpose: umlaut transliteration (`Müller` ≠ `Mueller`), abbreviations, word order.

## Error cases

| Situation | Result | Retry |
|---|---|---|
| Network error, timeout | Both checks `UNKNOWN / SOURCE_UNAVAILABLE` | Once, within the budget |
| HTTP 5xx | Both checks `UNKNOWN / SOURCE_UNAVAILABLE` | Once, within the budget |
| HTTP 4xx | Both checks `UNKNOWN / SOURCE_UNAVAILABLE`; the VIES error code from the body (if any) in `details.error`, otherwise `HTTP_4xx` | No |
| VIES error in the body (`MS_UNAVAILABLE`, `TIMEOUT`, `SERVICE_UNAVAILABLE`, `MS_MAX_CONCURRENT_REQ`, `GLOBAL_MAX_CONCURRENT_REQ`, `INVALID_INPUT`, …) | Both checks `UNKNOWN / SOURCE_UNAVAILABLE`, VIES code in `details.error` | No (SRS counts only network errors and 5xx as transient) |
| Answer without a boolean `valid` | Both checks `UNKNOWN / SOURCE_UNAVAILABLE`, `details.error = INVALID_RESPONSE` | No |

**Time budget:** at most 8 s per check request including the retry (REQ-INT-013, REQ-REL-003). The
adapter passes the remaining time as the `requests` timeout, and the runner (`checks/runner.py`) stops
waiting after 8 s in any case, so the API always answers in time.

## Terms of use

VIES is a public EC service for checking VAT numbers of intra-EU trading partners. The EC states that
VIES is a search engine over national databases and that results are not guaranteed; BizPartnerCheck's
disclaimer (REQ-FUNC-048) covers this. There is no published rate limit, but VIES answers with
`MS_MAX_CONCURRENT_REQ` / `GLOBAL_MAX_CONCURRENT_REQ` when overloaded, so we never retry those.

## Open points

- `TODO(SRS):` The endpoint and field names were taken from published descriptions of the VIES REST API;
  the official Swagger file (`ec.europa.eu/assets/taxud/vow-information/swagger_publicVAT.yaml`) could not
  be downloaded while writing this. Check it once and adjust this note if anything differs
  (REQ-POC-001 live demo).
- `TODO(SRS):` Terms-of-use review per REQ-COMP-004 still has to be recorded by the team.
- Sending our own VAT number as requester would give a `requestIdentifier` (consultation number) as extra
  evidence (REQ-FUNC-050 mentions "VIES request ID"). Needs a decision on which VAT number to send.
