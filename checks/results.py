"""Result values every check returns (SRS 3.2.4).

Plain Python without Django, so source adapters can use it outside the web app (REQ-MAINT-003).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

# Check values (SRS 3.2.4). UNKNOWN is never a pass or a fail.
TRUE = "TRUE"
FALSE = "FALSE"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"

# Reasons that go with UNKNOWN.
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
NO_DETAILS_FOUND = "NO_DETAILS_FOUND"


@dataclass(frozen=True)
class Partner:
    """The validated, normalized input of one check request (REQ-FUNC-030)."""

    vat_number: str
    company_name: str
    company_register_number: str = ""
    address: str = ""
    required_license_codes: tuple[str, ...] = ()
    requesting_organization_vat_number: str = ""

    @property
    def country_code(self):
        return self.vat_number[:2]


@dataclass(frozen=True)
class CheckResult:
    """One entry of the "checks" list in the response (SRS Appendix B)."""

    check: str
    result: str
    source: str
    data_timestamp: datetime | None = None
    reason: str | None = None
    details: dict = field(default_factory=dict)
    # Only list-based sources set it: True when the synced list is older than 48 h (REQ-FUNC-073).
    stale: bool | None = None

    def to_json(self):
        data = {"check": self.check, "result": self.result}
        if self.reason:
            data["reason"] = self.reason
        data["source"] = self.source
        # dataTimestamp is omitted for NOT_APPLICABLE (SRS 3.2.4).
        if self.data_timestamp and self.result != NOT_APPLICABLE:
            data["dataTimestamp"] = format_utc(self.data_timestamp)
        if self.stale is not None:
            data["stale"] = self.stale
        if self.details:
            data["details"] = self.details
        return data


# The value each check must have to count as passed (SRS 3.2.4). onHfuList is informational and left out
# (REQ-FUNC-034): not being listed is normal, so it never counts as a pass or a fail.
EXPECTED_VALUES = {
    "vatValid": TRUE,
    "nameMatchesVat": TRUE,
    "listedAsFakeCompany": FALSE,
    "inCompanyRegister": TRUE,
    "inBusinessLicenseRegister": TRUE,
    "hasRequiredLicenses": TRUE,
}
INFORMATIONAL_CHECKS = {"onHfuList"}


def all_checks_passed(checks):
    """REQ-FUNC-047: True only if every applicable check has its expected value.

    `checks` are the response entries ({"check": ..., "result": ...}). NOT_APPLICABLE and informational checks
    are skipped; UNKNOWN never equals an expected value, so it makes the summary False. A check missing from
    EXPECTED_VALUES also makes it False, so a new check can't count as passed before its expected value is set.
    """
    return all(
        entry["result"] == EXPECTED_VALUES.get(entry["check"])
        for entry in checks
        if entry["result"] != NOT_APPLICABLE and entry["check"] not in INFORMATIONAL_CHECKS
    )


def utc_now():
    return datetime.now(UTC)


def format_utc(moment):
    """ISO 8601 in UTC with a trailing Z, as in SRS Appendix B."""
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
