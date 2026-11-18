"""Stored check requests: the evidence that a partner was checked (REQ-FUNC-050, REQ-FUNC-041, REQ-FUNC-051).

Stores structured records only, never documents (C7). Stored requests are immutable; they can only be
deleted as a whole. Every accepted request is stored, also when results are UNKNOWN. Where each evidence
field of REQ-FUNC-050 (SRS OD-02) is kept:

- request ID, organization, requesting user, channel, token name: CheckRequest.id, .organization,
  .requested_by / .requested_by_name, .channel, .token_name
- input: CheckRequest.vat_number, .company_name, .company_register_number, .address,
  .required_license_codes, .reference
- received/completed timestamps: CheckRequest.received_at, .completed_at (UTC)
- all results with details: one CheckRequestResult per check (result, reason, source, details)
- sync timestamps of the lists used: CheckRequestResult.data_timestamp, which for a list source (BMF, HFU)
  is the time of the sync that the result is based on (SRS 3.2.4, Appendix B)
- references the source returns: CheckRequestResult.details, e.g. details.requestIdentifier from VIES
"""

import uuid

from django.conf import settings
from django.db import models

from accounts.models import Organization

from .results import NOT_APPLICABLE, format_utc


class ImmutableModel(models.Model):
    """Can be created and deleted, but never changed after it was saved (REQ-FUNC-051).

    Only save() is guarded. QuerySet.update() and bulk_update() bypass it and would change stored
    evidence, so never use them on these models.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(f"Stored {type(self).__name__} records cannot be changed.")
        super().save(*args, **kwargs)


class CheckRequest(ImmutableModel):
    """One partner check request with its input; the results are CheckRequestResult rows."""

    CHANNEL_API = "api"
    CHANNEL_WEB = "web"

    # The UUID is the requestId of the API response.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="check_requests")
    # A deleted user leaves the request in place, with their name kept as evidence (REQ-COMP-002).
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="check_requests"
    )
    requested_by_name = models.CharField(max_length=300)
    channel = models.CharField(max_length=3, choices=[(CHANNEL_API, "API"), (CHANNEL_WEB, "Web")])
    # Name of the API token, never its value (REQ-FUNC-045); empty for calls with a web session.
    token_name = models.CharField(max_length=100, blank=True)

    vat_number = models.CharField(max_length=20)
    company_name = models.CharField(max_length=200)
    company_register_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    required_license_codes = models.JSONField(default=list, blank=True)
    reference = models.CharField(max_length=200, blank=True)

    received_at = models.DateTimeField()
    completed_at = models.DateTimeField()

    class Meta:
        # Requests are always listed per organization, newest first (REQ-PERF-005).
        indexes = [models.Index(fields=["organization", "-received_at"])]
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.vat_number} {self.received_at:%Y-%m-%d %H:%M}"

    def to_json(self):
        """The stored request in the response shape of SRS Appendix B (REQ-FUNC-045), without disclaimer."""
        partner = {"companyName": self.company_name, "vatNumber": self.vat_number}
        if self.company_register_number:
            partner["companyRegisterNumber"] = self.company_register_number
        if self.address:
            partner["address"] = self.address
        if self.required_license_codes:
            partner["requiredLicenseCodes"] = self.required_license_codes
        data = {
            "requestId": str(self.id),
            "receivedAt": format_utc(self.received_at),
            "completedAt": format_utc(self.completed_at),
            "organization": self.organization.name,
            "requestedBy": {
                "user": self.requested_by_name,
                "channel": self.channel,
                "tokenName": self.token_name or None,
            },
            "partner": partner,
        }
        if self.reference:
            data["reference"] = self.reference
        data["checks"] = [result.to_json() for result in self.results.all()]
        return data


class CheckRequestResult(ImmutableModel):
    """The result of one check within a request (SRS 3.2.4); one row per check, so results can be filtered."""

    request = models.ForeignKey(CheckRequest, on_delete=models.CASCADE, related_name="results")
    position = models.PositiveSmallIntegerField()
    check_name = models.CharField(max_length=50)
    result = models.CharField(max_length=20)
    reason = models.CharField(max_length=30, blank=True)
    source = models.CharField(max_length=30)
    data_timestamp = models.DateTimeField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["request", "check_name"], name="one_result_per_check")]

    def __str__(self):
        return f"{self.check_name}: {self.result}"

    def to_json(self):
        data = {"check": self.check_name, "result": self.result}
        if self.reason:
            data["reason"] = self.reason
        data["source"] = self.source
        if self.data_timestamp and self.result != NOT_APPLICABLE:
            data["dataTimestamp"] = format_utc(self.data_timestamp)
        if self.details:
            data["details"] = self.details
        return data


class FakeCompany(models.Model):
    """One entry of the BMF list of sham companies (REQ-FUNC-033), as imported by the daily sync (REQ-FUNC-070).

    Only the fields the check needs are stored; dates of birth of listed persons are left out (REQ-COMP-001,
    docs/sources/bmf.md). VAT number and FN are indexed because they are the first two matching keys.
    """

    name = models.CharField(max_length=300)
    company_register_number = models.CharField(max_length=20, blank=True, db_index=True)
    vat_number = models.CharField(max_length=20, blank=True, db_index=True)
    address = models.TextField(blank=True)
    # "Veröffentlichung" in the feed: the day BMF published the entry.
    date_listed = models.DateField()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "fake companies"

    def __str__(self):
        return self.name


class SyncLog(models.Model):
    """One run of a list sync, successful or not (REQ-FUNC-072). Written by the sync job only."""

    SOURCE_BMF = "BMF"
    OUTCOME_SUCCESS = "success"
    OUTCOME_FAILED = "failed"

    source = models.CharField(max_length=30, choices=[(SOURCE_BMF, "BMF fake-company list")])
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    outcome = models.CharField(max_length=10, choices=[(OUTCOME_SUCCESS, "Success"), (OUTCOME_FAILED, "Failed")])
    number_of_entries = models.PositiveIntegerField(default=0)
    # The feed's own <lastBuildDate>, which is a date without a time (docs/sources/bmf.md); empty if the run
    # failed before it was read.
    feed_timestamp = models.DateField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["source", "outcome", "-start_time"])]
        ordering = ["-start_time"]

    def __str__(self):
        return f"{self.source} {self.start_time:%Y-%m-%d %H:%M} {self.outcome}"

    @classmethod
    def last_success(cls, source):
        """The newest successful run of a source, or None; the base for the 48 h stale flag (REQ-FUNC-073)."""
        return cls.objects.filter(source=source, outcome=cls.OUTCOME_SUCCESS).first()
