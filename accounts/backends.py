from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.signals import user_login_failed
from django.core.exceptions import SuspiciousOperation
from django.dispatch import receiver
from django.urls import reverse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from . import lockout


class KeycloakBackend(OIDCAuthenticationBackend):
    """Login through Keycloak. Accounts are matched by email address and created on the first login.

    Keycloak owns passwords, password reset, email verification and its own brute-force lockout.
    """

    def verify_claims(self, claims):
        # Only addresses Keycloak has confirmed, so nobody can claim an invitation sent to someone else's email.
        return super().verify_claims(claims) and claims.get("email_verified") is True

    def filter_users_by_claims(self, claims):
        users = super().filter_users_by_claims(claims)
        # Staff log in only with their password on /admin/, so a Keycloak account can't take over the Super Admin.
        if any(user.is_staff or user.is_superuser for user in users):
            raise SuspiciousOperation("Staff accounts can't log in through Keycloak")
        return users

    def get_user(self, user_id):
        # Unlike Django's own backend, the library doesn't check is_active, so a deactivated member's open session
        # would otherwise keep working until it expires.
        user = super().get_user(user_id)
        return user if user and user.is_active else None

    def create_user(self, claims):
        # No organization and no roles yet: the user registers an organization or accepts an invitation next.
        return self.UserModel.objects.create_user(
            email=claims["email"],
            first_name=claims.get("given_name", ""),
            last_name=claims.get("family_name", ""),
        )


def keycloak_logout_url(request):
    """End the Keycloak session too, then come back to the home page."""
    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": request.build_absolute_uri(reverse(settings.LOGOUT_REDIRECT_URL)),
    }
    if request.session.get("oidc_id_token"):
        params["id_token_hint"] = request.session["oidc_id_token"]
    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(params)}"


class LockoutBackend(ModelBackend):
    """Django's normal email + password login for the admin site, refusing accounts that are locked (REQ-SEC-004).

    Users without a usable password (everyone who logs in through Keycloak) can't get in this way.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get(get_user_model().USERNAME_FIELD)
        if email and lockout.is_locked(email):
            return None
        user = super().authenticate(request, username, password, **kwargs)
        if user is not None and email:
            lockout.clear(email)
        return user


@receiver(user_login_failed)
def count_failed_login(sender, credentials, **kwargs):
    """Count every failed login, whichever page it came from."""
    email = credentials.get("username") or credentials.get(get_user_model().USERNAME_FIELD)
    if email:
        lockout.record_failure(email)
