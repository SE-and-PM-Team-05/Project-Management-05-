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

    def to_json(self):
        data = {"check": self.check, "result": self.result}
        if self.reason:
            data["reason"] = self.reason
        data["source"] = self.source
        # dataTimestamp is omitted for NOT_APPLICABLE (SRS 3.2.4).
        if self.data_timestamp and self.result != NOT_APPLICABLE:
            data["dataTimestamp"] = format_utc(self.data_timestamp)
        if self.details:
            data["details"] = self.details
        return data


def utc_now():
    return datetime.now(UTC)


def format_utc(moment):
    """ISO 8601 in UTC with a trailing Z, as in SRS Appendix B."""
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
