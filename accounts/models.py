import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class Organization(models.Model):
    """A customer company; every user except the Super Admin belongs to exactly one."""

    name = models.CharField(max_length=200)
    address = models.TextField()
    vat_number = models.CharField("VAT number", max_length=14)
    is_verified = models.BooleanField(default=False, help_text="Set when the registration email link is opened.")
    terms_accepted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """A person who logs in with their email address instead of a username."""

    username = None
    email = models.EmailField("email address", unique=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, null=True, blank=True, related_name="users"
    )
    # Organization roles add up (SRS 2.5); the Super Admin has none and no organization.
    is_org_admin = models.BooleanField("Org Admin", default=False)
    is_request_user = models.BooleanField("Request User", default=False)
    is_review_user = models.BooleanField("Review User", default=False)
    must_change_password = models.BooleanField(
        default=False,
        help_text="Set for one-time passwords; the user is sent to the password change page until they change it.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.must_change_password = False

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.is_active:
            # Deactivating a user revokes all their API tokens for good; reactivating does not bring them back
            # (REQ-FUNC-023). Deleting a user deletes the tokens through the foreign key.
            self.api_tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())

    def __str__(self):
        return self.email


def invitation_expiry():
    return timezone.now() + timedelta(days=7)


class Invitation(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)

    is_org_admin = models.BooleanField(default=False)
    is_request_user = models.BooleanField(default=False)
    is_review_user = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=invitation_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.email} - {self.organization.name}"

    def is_valid(self):
        return self.accepted_at is None and self.revoked_at is None and timezone.now() < self.expires_at


class ApiToken(models.Model):
    """A named API token of one user (REQ-FUNC-020, REQ-FUNC-022, REQ-SEC-002).

    Only the SHA-256 hash of the value is stored; the full value is shown once, when the token is created.
    Afterwards only the name, the first 8 characters, the owner and the dates are visible.
    """

    PREFIX_LENGTH = 8

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=PREFIX_LENGTH, help_text="First 8 characters of the value.")
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    # Tokens never expire unless an expiry is set (REQ-FUNC-020).
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @staticmethod
    def hash_value(value):
        return hashlib.sha256(value.encode()).hexdigest()

    @classmethod
    def issue(cls, user, name, created_by, expires_at=None):
        """Create a token and return it together with its full value, which is not stored anywhere."""
        # 40 random bytes = 320 bits, so the part after the visible 8-character prefix alone still has
        # 272 bits (REQ-SEC-002 asks for at least 256).
        value = secrets.token_urlsafe(40)
        token = cls.objects.create(
            user=user,
            name=name,
            prefix=value[: cls.PREFIX_LENGTH],
            token_hash=cls.hash_value(value),
            created_by=created_by,
            expires_at=expires_at,
        )
        return token, value

    def is_active(self):
        return self.revoked_at is None and (self.expires_at is None or timezone.now() < self.expires_at)

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])
