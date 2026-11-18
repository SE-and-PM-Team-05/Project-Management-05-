"""Bearer-token authentication for the API (REQ-INT-011, REQ-FUNC-020…023, SCRUM-71).

A client sends `Authorization: Bearer <token>`. The token is looked up by its SHA-256 hash on every request, so a
revoked or expired token, or a token of a deactivated user, is rejected on the very next call (REQ-FUNC-023 asks for
60 s). The request then runs as the token's owner with the owner's roles at the time of the call (REQ-FUNC-021).
"""

from datetime import timedelta

from django.utils import timezone

from .models import ApiToken

# last_used_at is written at most once a minute per token, so busy clients don't cause a write on every call.
LAST_USED_RESOLUTION = timedelta(minutes=1)


def bearer_value(header):
    """The token from an `Authorization: Bearer <token>` header, or None if the header has another form."""
    scheme, _, value = header.strip().partition(" ")
    value = value.strip()
    if scheme.lower() != "bearer" or not value or " " in value:
        return None
    return value


def authenticate_token(value):
    """Return the usable ApiToken for a full token value, or None.

    None means unknown, revoked, expired or owned by a deactivated user; the caller answers all of them with the
    same 401, so a client learns nothing about which tokens exist.
    """
    token = ApiToken.objects.select_related("user").filter(token_hash=ApiToken.hash_value(value)).first()
    # The user check also covers users deactivated without User.save(), e.g. by QuerySet.update().
    if token is None or not token.is_active() or not token.user.is_active:
        return None
    now = timezone.now()
    if token.last_used_at is None or now - token.last_used_at >= LAST_USED_RESOLUTION:
        token.last_used_at = now
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
    return token
