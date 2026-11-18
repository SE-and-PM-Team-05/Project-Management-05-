from django import forms
from django.db import transaction
from django.utils import timezone

from .models import Organization, User
from .tokens import LATEST_EXPIRY_DATE
from .validators import normalize_vat_number, validate_vat_number


class RegistrationForm(forms.Form):
    """Registers an organization for the logged-in user, who becomes its first user (REQ-FUNC-001, REQ-COMP-003).

    Name, email and password come from Keycloak, which has already verified the email address.
    """

    organization_name = forms.CharField(max_length=200)
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    vat_number = forms.CharField(label="VAT number", max_length=20, help_text="e.g. ATU12345678")
    accept_terms = forms.BooleanField(
        label="I accept the terms of use, including that BizPartnerCheck carries no liability for my decisions"
    )

    def clean_vat_number(self):
        vat = normalize_vat_number(self.cleaned_data["vat_number"])
        validate_vat_number(vat)
        return vat

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
