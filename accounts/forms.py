import logging
import time

from django import forms
from django.db import transaction
from django.utils import timezone

from checks.runner import SOURCE_TIME_BUDGET
from checks.sources.vies import ViesUnavailable, query_vies

from .models import Organization, User
from .tokens import LATEST_EXPIRY_DATE
from .validators import normalize_vat_number, validate_vat_number

logger = logging.getLogger(__name__)


def verify_own_vat_number(vat_number):
    """Ask VIES about the registering organization's own VAT number (REQ-FUNC-004).

    Returns the UTC time VIES confirmed the number, or None if VIES gave no usable answer, in which case the
    organization is registered as "VAT unverified". Raises ValidationError if VIES reports the number invalid.
    Same 8 s budget and single retry as a check request (REQ-INT-013, REQ-REL-003).
    """
    try:
        data, queried_at = query_vies(vat_number, time.monotonic() + SOURCE_TIME_BUDGET)
    except ViesUnavailable as error:
        logger.warning("VIES could not verify VAT number %s at registration: %s", vat_number, error.code)
        return None
    if not data["valid"]:
        raise forms.ValidationError(
            "VIES, the EU's VAT number register, reports %(vat)s as not valid. "
            "Enter your organization's own VAT number exactly as it appears on your invoices.",
            code="vies_invalid",
            params={"vat": vat_number},
        )
    return queried_at


class RegistrationForm(forms.Form):
    """Registers an organization for the logged-in user, who becomes its first user (REQ-FUNC-001, REQ-COMP-003).

    Name, email and password come from Keycloak, which has already verified the email address. The VAT number is
    checked with VIES (REQ-FUNC-004): invalid numbers are rejected; if VIES does not answer, the organization is
    registered as "VAT unverified".
    """

    organization_name = forms.CharField(max_length=200)
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    vat_number = forms.CharField(label="VAT number", max_length=20, help_text="e.g. ATU12345678")
    accept_terms = forms.BooleanField(
        label="I accept the terms of use, including that BizPartnerCheck carries no liability for my decisions"
    )

    def clean_vat_number(self):
        vat = normalize_vat_number(self.cleaned_data["vat_number"])
        validate_vat_number(vat)  # format only; VIES is asked in clean()
        return vat

    def clean(self):
        cleaned = super().clean()
        # VIES is asked last and only when every field is valid, so a missing field never waits up to 8 s for
        # VIES and a corrected submit doesn't ask it again for nothing.
        if not self.errors:
            try:
                self.vat_verified_at = verify_own_vat_number(cleaned["vat_number"])
            except forms.ValidationError as error:
                self.add_error("vat_number", error)
        return cleaned

    @transaction.atomic
    def save(self, user):
        """Return the new organization, or None if the user joined one meanwhile (e.g. a double submit)."""
        user = User.objects.select_for_update().get(pk=user.pk)
        if user.organization_id:
            return None
        data = self.cleaned_data
        user.organization = Organization.objects.create(
            name=data["organization_name"],
            address=data["address"],
            vat_number=data["vat_number"],
            vat_verified_at=self.vat_verified_at,
            is_verified=True,
            terms_accepted_at=timezone.now(),
        )
        user.is_org_admin = user.is_request_user = user.is_review_user = True
        user.save(update_fields=["organization", "is_org_admin", "is_request_user", "is_review_user"])
        return user.organization


class InvitationForm(forms.Form):
    email = forms.EmailField()

    is_org_admin = forms.BooleanField(required=False, label="Org Admin")
    is_request_user = forms.BooleanField(required=False, label="Request User")
    is_review_user = forms.BooleanField(required=False, label="Review User")

    def clean(self):
        cleaned = super().clean()

        if not any(
            [
                cleaned.get("is_org_admin"),
                cleaned.get("is_request_user"),
                cleaned.get("is_review_user"),
            ]
        ):
            raise forms.ValidationError("Select at least one role.")

        return cleaned


class MemberEditForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)

    is_org_admin = forms.BooleanField(required=False, label="Org Admin")
    is_request_user = forms.BooleanField(required=False, label="Request User")
    is_review_user = forms.BooleanField(required=False, label="Review User")

    def clean(self):
        cleaned = super().clean()

        if not any(
            [
                cleaned.get("is_org_admin"),
                cleaned.get("is_request_user"),
                cleaned.get("is_review_user"),
            ]
        ):
            raise forms.ValidationError("Select at least one role.")

        return cleaned


class ApiTokenForm(forms.Form):
    """Create an API token (REQ-FUNC-020); the owner field is only offered to Org Admins."""

    name = forms.CharField(max_length=100, help_text="e.g. the system that will use it, such as “ERP prod”")
    owner = forms.ModelChoiceField(queryset=User.objects.none(), empty_label=None)
    expires_on = forms.DateField(
        label="Expires on (optional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Leave empty for a token that works until it is revoked. It stops working at the end of this day.",
    )

    def __init__(self, *args, owners, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = owners
        if owners.count() <= 1:
            # A user without the Org Admin role can only create tokens for themselves.
            self.fields["owner"].widget = forms.HiddenInput()
            self.fields["owner"].initial = owners.first()

    def clean_expires_on(self):
        day = self.cleaned_data["expires_on"]
        if day and day < timezone.localdate():
            raise forms.ValidationError("The expiry date must not be in the past.")
        if day and day > LATEST_EXPIRY_DATE:
            raise forms.ValidationError(f"The expiry date must be in {LATEST_EXPIRY_DATE.year} or earlier.")
        return day
