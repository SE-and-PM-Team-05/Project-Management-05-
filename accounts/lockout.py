"""Lock an account for 15 minutes after 5 failed logins (REQ-SEC-004).

Failures are counted per email address in one database row (accounts.models.LoginFailure), which every app
process shares. The count is raised by a single UPDATE that adds 1 in the database (SCRUM-54), so failed logins
that arrive at the same moment are each counted: PostgreSQL makes simultaneous UPDATEs of one row wait for each
other, and the second sees the first's count.

Each counted failure restarts the 15-minute window. Once an account is locked, further attempts are refused
without being counted, so the lock ends 15 minutes after the fifth failure.
"""

from datetime import timedelta

from django.db.models import Case, F, Q, Value, When
from django.utils import timezone

from .models import LoginFailure

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _key(email):
    return email.strip().lower()


def _window_start():
    """Failures before this moment no longer count."""
    return timezone.now() - timedelta(seconds=LOCKOUT_SECONDS)


def failed_attempts(email):
    row = LoginFailure.objects.filter(email=_key(email), last_failed_at__gte=_window_start()).first()
    return row.count if row else 0


def is_locked(email):
    return failed_attempts(email) >= MAX_FAILED_ATTEMPTS


def record_failure(email):
    now = timezone.now()
    expired = Q(last_failed_at__lt=now - timedelta(seconds=LOCKOUT_SECONDS))
    # Make sure the row exists; ON CONFLICT DO NOTHING, so a simultaneous insert is no error.
    LoginFailure.objects.bulk_create(
        [LoginFailure(email=_key(email), count=0, last_failed_at=now)], ignore_conflicts=True
    )
    # One atomic step: below the limit add 1, after an expired window start again at 1, during a lock change nothing.
    LoginFailure.objects.filter(Q(email=_key(email)) & (Q(count__lt=MAX_FAILED_ATTEMPTS) | expired)).update(
        count=Case(When(expired, then=Value(1)), default=F("count") + 1),
        last_failed_at=now,
    )


def clear(email):
    LoginFailure.objects.filter(email=_key(email)).delete()
