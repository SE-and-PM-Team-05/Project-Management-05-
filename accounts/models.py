from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


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

    def __str__(self):
        return self.email
