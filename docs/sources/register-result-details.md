# Result details: Firmenbuch and GISA checks

Agreed format of the `details` object for the three register checks built in Sprint 3. The adapters fill it
(Antonia: SCRUM-43, Maryam: SCRUM-44) and the HTML result page shows it (Luka: SCRUM-45). Every check result
already has the fixed fields `check`, `result`, `reason`, `source` and `dataTimestamp` (`checks/results.py`,
REQ-FUNC-045); this page only covers `details`.

Change this page in a pull request before changing the keys in code, so all three stay in step.

## Rules (same as the existing VIES, BMF and HFU checks)

- Keys are camelCase English; values are copied from the register as they are (no translation).
- Empty strings and missing values are left out, as in `entry_details` in `checks/sources/bmf.py`. The one
  exception is the lists named on this page (`licenses`, `requiredLicenseCodes`, `missingLicenseCodes`): they
  are always included when the table says so, even when empty, because an empty list is itself the answer.
- Dates are ISO 8601 (`2026-11-19`).
- The FN is called `companyRegisterNumber`, as in the check input and the BMF check, written like the input
  stores it: no spaces, lowercase check letter, no "FN" prefix (`123456a`).
- Why a result is UNKNOWN goes in `reason` (SOURCE_UNAVAILABLE, AMBIGUOUS_MATCH, NO_DETAILS_FOUND), not in `details`.
- NOT_APPLICABLE results have no `details`.

## `inCompanyRegister` (Firmenbuch, REQ-FUNC-035)

| Key | Type | When | Example |
|---|---|---|---|
| `companyRegisterNumber` | string | found | `"123456a"` |
| `registeredName` | string | found | `"Muster Bau GmbH"` |
| `legalForm` | string | found | `"GmbH"` |
| `registeredAddress` | string | found, if the register has it | `"Hauptstraße 1, 1010 Wien"` |
| `status` | `"active"` or `"deleted"` | found | `"active"` |
| `deletedOn` | date | only when `status` is `"deleted"` | `"2025-03-31"` |
| `matchedBy` | `"companyRegisterNumber"` or `"vatNumber"` | found | `"vatNumber"` |
| `candidates` | list of `{companyRegisterNumber, registeredName, legalForm}` | only for UNKNOWN / AMBIGUOUS_MATCH | see below |

- TRUE: found and `status` is `"active"`.
- FALSE: found and `"deleted"`, or not found. When nothing is found, `details` is empty.
- `status` has only these two values. Any other state the register reports (for example a company in
  liquidation) is still a registration, so `status` is `"active"` and the register's own wording goes in
  `statusText` (string, only in that case).
- Firmenbuch unavailable: UNKNOWN / SOURCE_UNAVAILABLE, no `details`.

## `inBusinessLicenseRegister` (GISA, REQ-FUNC-036)

| Key | Type | When | Example |
|---|---|---|---|
| `licenses` | list of licenses (below) | always for TRUE and FALSE | |
| `matchedBy` | `"vatNumber"`, `"companyRegisterNumber"` or `"name"` | partner found in GISA | `"vatNumber"` |

Each license (only active licenses are listed):

| Key | Type | Example |
|---|---|---|
| `gisaNumber` | string | `"12345678"` |
| `licenseCode` | string, the code a caller passes in `requiredLicenseCodes` | `"BAUMEISTER"` |
| `name` | string, the license wording from GISA | `"Baumeister"` |
| `responsiblePerson` | string | `"Maria Muster"` |
| `activeSince` | date | `"2019-05-02"` |

- TRUE: at least one active license. FALSE: `licenses` is `[]`; if the partner isn't in GISA at all,
  `matchedBy` is left out.
- A match by name only is never definite (SRS UC-04, 4c): the result is UNKNOWN / AMBIGUOUS_MATCH with
  `matchedBy: "name"` and the licenses found, so a person can judge.
- GISA unavailable: UNKNOWN / SOURCE_UNAVAILABLE, no `details`; `hasRequiredLicenses` is then UNKNOWN too.

## `hasRequiredLicenses` (GISA, REQ-FUNC-037)

| Key | Type | When | Example |
|---|---|---|---|
| `requiredLicenseCodes` | list of strings, as the caller sent them | TRUE and FALSE | `["BAUMEISTER", "ZIMMERMEISTER"]` |
| `missingLicenseCodes` | list of strings | TRUE (`[]`) and FALSE | `["ZIMMERMEISTER"]` |

- TRUE: `missingLicenseCodes` is `[]`. FALSE: it names the missing codes. Without `requiredLicenseCodes` in
  the request the check is NOT_APPLICABLE.
- Codes are compared ignoring case and surrounding spaces; `requiredLicenseCodes` and `missingLicenseCodes`
  repeat the codes exactly as the caller sent them. Which codes count as "necessary" stays the caller's choice
  (SRS OD-03).

## Example

The `checks` entries for an active Austrian company checked with one required license it doesn't hold. Luka can
use this as test data for the result page before the adapters exist.

```json
[
  {
    "check": "inCompanyRegister", "result": "TRUE", "source": "Firmenbuch",
    "dataTimestamp": "2026-11-19T09:42:12Z",
    "details": {
      "companyRegisterNumber": "123456a", "registeredName": "Muster Bau GmbH", "legalForm": "GmbH",
      "registeredAddress": "Hauptstraße 1, 1010 Wien", "status": "active", "matchedBy": "vatNumber"
    }
  },
  {
    "check": "inBusinessLicenseRegister", "result": "TRUE", "source": "GISA",
    "dataTimestamp": "2026-11-19T09:42:13Z",
    "details": {
      "matchedBy": "vatNumber",
      "licenses": [
        { "gisaNumber": "12345678", "licenseCode": "BAUMEISTER", "name": "Baumeister",
          "responsiblePerson": "Maria Muster", "activeSince": "2019-05-02" }
      ]
    }
  },
  {
    "check": "hasRequiredLicenses", "result": "FALSE", "source": "GISA",
    "dataTimestamp": "2026-11-19T09:42:13Z",
    "details": { "requiredLicenseCodes": ["BAUMEISTER", "ZIMMERMEISTER"], "missingLicenseCodes": ["ZIMMERMEISTER"] }
  }
]
```

## Open points

- The example values (license codes, GISA number format) are made up. Antonia and Maryam replace them with real
  ones after the first live lookup (SCRUM-80, SCRUM-84) and note the register field each key comes from.
- SRS Appendix B shows `"fn"` in the `inCompanyRegister` example. It is informative only; it should be changed to
  `companyRegisterNumber` the next time the SRS is updated.
