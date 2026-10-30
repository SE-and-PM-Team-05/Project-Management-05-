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


class User(AbstractUser):
    """A person who logs in with their email address instead of a username."""

    username = None
    email = models.EmailField("email address", unique=True)
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
