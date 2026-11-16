from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from . import lockout


class LockoutBackend(ModelBackend):
    """Django's normal email + password login, refusing accounts that are locked (REQ-SEC-004).

    Used for every login, including the admin, so a locked account can't be bypassed through another page.
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
