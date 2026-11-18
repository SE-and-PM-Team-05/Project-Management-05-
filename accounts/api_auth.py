"""Bearer-token authentication and the per-token rate limit for the API (SCRUM-71, SCRUM-73).

A client sends `Authorization: Bearer <token>`. The token is looked up by its SHA-256 hash on every request, so a
revoked or expired token, or a token of a deactivated user, is rejected on the very next call (REQ-FUNC-023 asks for
60 s). The request then runs as the token's owner with the owner's roles at the time of the call (REQ-FUNC-021).

Each token may make RATE_LIMIT calls per window of RATE_WINDOW (REQ-SEC-003). A window starts with the first call
after the previous one ended. The count lives on the token row and is changed under a row lock, so it is exact even
when several app processes serve the same token at once.
"""

import math
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ApiToken

RATE_LIMIT = 200
RATE_WINDOW = timedelta(minutes=1)


@dataclass(frozen=True)
class Quota:
    """The token's rate-limit state after this call, for the response headers."""

    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int  # until the current window ends; also the Retry-After value of a 429


def bearer_value(header):
    """The token from an `Authorization: Bearer <token>` header, or None if the header has another form."""
    scheme, _, value = header.strip().partition(" ")
    value = value.strip()
    if scheme.lower() != "bearer" or not value or " " in value:
        return None
    return value


def authenticate_token(value):
    """Return (token, quota) for a usable token, or None.

    None means unknown, revoked, expired or owned by a deactivated user; the caller answers all of them with the
    same 401, so a client learns nothing about which tokens exist. A usable token over its limit comes back with
    quota.allowed False; such calls are not counted and do not change the last-use date.
    """
    with transaction.atomic():
        token = (
            ApiToken.objects.select_for_update(of=("self",))
            .select_related("user")
            .filter(token_hash=ApiToken.hash_value(value))
            .first()
        )
        # The user check also covers users deactivated without User.save(), e.g. by QuerySet.update().
        if token is None or not token.is_active() or not token.user.is_active:
            return None
        return token, count_call(token, timezone.now())


def count_call(token, now):
    """Count one call in the token's current window and save it; the caller holds the row lock."""
    if token.rate_window_started_at is None or now >= token.rate_window_started_at + RATE_WINDOW:
        token.rate_window_started_at = now
        token.rate_window_count = 0
    allowed = token.rate_window_count < RATE_LIMIT
    if allowed:
        token.rate_window_count += 1
        token.last_used_at = now
        token.save(update_fields=["rate_window_started_at", "rate_window_count", "last_used_at"])
    seconds_left = (token.rate_window_started_at + RATE_WINDOW - now).total_seconds()
    return Quota(
        allowed=allowed,
        limit=RATE_LIMIT,
        remaining=RATE_LIMIT - token.rate_window_count,
        reset_seconds=max(1, math.ceil(seconds_left)),
    )
