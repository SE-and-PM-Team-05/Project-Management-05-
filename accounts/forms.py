from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from . import lockout
from .models import Organization, User
from .validators import normalize_vat_number, validate_vat_number


class RegistrationForm(forms.Form):
    """Registers an organization and its first user (REQ-FUNC-001, REQ-COMP-003)."""

    organization_name = forms.CharField(max_length=200)
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    vat_number = forms.CharField(label="VAT number", max_length=20, help_text="e.g. ATU12345678")
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput, strip=False)
    accept_terms = forms.BooleanField(
        label="I accept the terms of use, including that BizPartnerCheck carries no liability for my decisions"
    )

    def clean_vat_number(self):
        vat = normalize_vat_number(self.cleaned_data["vat_number"])
        validate_vat_number(vat)
        return vat

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        elif password1:
            candidate = User(
                email=cleaned.get("email", ""),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                validate_password(password1, candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        organization = Organization.objects.create(
            name=data["organization_name"],
            address=data["address"],
            vat_number=data["vat_number"],
            terms_accepted_at=timezone.now(),
        )
        # Inactive until the email link is opened, so an unverified admin cannot log in.
        return User.objects.create_user(
            email=data["email"],
            password=data["password1"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            organization=organization,
            is_active=False,
            is_org_admin=True,
            is_request_user=True,
            is_review_user=True,
        )


class ResendVerificationForm(forms.Form):
    email = forms.EmailField()


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


class AcceptInvitationForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label="Repeat password",
        widget=forms.PasswordInput,
    )

    def clean(self):
        cleaned = super().clean()

        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        elif password1:
            candidate = User(
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                validate_password(password1, candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)

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


class LoginForm(AuthenticationForm):
    """Login that tells a locked-out user why, instead of the generic error (REQ-SEC-004)."""

    def clean(self):
        email = self.cleaned_data.get("username")
        if email and lockout.is_locked(email):
            raise forms.ValidationError(
                "Too many failed login attempts. Your account is locked for 15 minutes.", code="locked"
            )
        return super().clean()


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
        return day
