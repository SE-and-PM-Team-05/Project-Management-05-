"""Stored check requests: the evidence that a partner was checked (REQ-FUNC-050, REQ-FUNC-041, REQ-FUNC-051).

Stores structured records only, never documents (C7). Stored requests are immutable; they can only be
deleted as a whole. Which further fields count as legal proof is still open (SRS OD-02); for now the
request stores exactly what the API response shows.
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
    # Name of the API token, never its value (REQ-FUNC-045); empty until tokens exist (SCRUM-48).
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
