"""Lock an account for 15 minutes after 5 failed logins (REQ-SEC-004).

Failures are counted per email address in Django's cache, which is the database cache, so every app process
shares the same count. Each failure restarts the 15-minute window. Once an account is locked, further attempts
are refused without being counted, so the lock ends 15 minutes after the fifth failure.
"""

from django.core.cache import cache

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _key(email):
    return f"login-failures:{email.strip().lower()}"


def failed_attempts(email):
    return cache.get(_key(email), 0)


def is_locked(email):
    return failed_attempts(email) >= MAX_FAILED_ATTEMPTS


def record_failure(email):
    count = failed_attempts(email)
    if count < MAX_FAILED_ATTEMPTS:
        cache.set(_key(email), count + 1, LOCKOUT_SECONDS)


def clear(email):
    cache.delete(_key(email))
