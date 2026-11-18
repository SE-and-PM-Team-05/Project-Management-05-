"""HTTP calls to a source within its time budget, with one retry (REQ-INT-013, REQ-REL-003).

Shared by all adapters that call a web service, so every source retries the same way. Plain Python
without Django (REQ-MAINT-003).
"""

import logging
import time

import requests

from ..results import utc_now

logger = logging.getLogger(__name__)


class SourceUnavailable(Exception):
    """The source gave no usable answer; `code` is a short, language-neutral reason, e.g. "TIMEOUT"."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def post_within_budget(url, deadline, source="source", **kwargs):
    """POST to `url` and return (response, UTC time of the attempt that answered).

    A transient error (network error, timeout, HTTP 5xx) is retried once if time is left before
    `deadline`, a time.monotonic() value (REQ-REL-003). Each attempt gets only the time that is left, so
    both attempts together stay within the budget (REQ-INT-013). Any answer below HTTP 500 is returned for
    the adapter to read; raises SourceUnavailable when none arrives in time.

    `kwargs` go to requests.post (json=, data=, headers=); `source` names the source in the log.
    """
    error = "TIMEOUT"
    for attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        queried_at = utc_now()
        try:
            response = requests.post(url, timeout=remaining, **kwargs)
        except requests.Timeout:
            error = "TIMEOUT"
        except requests.RequestException:
            error = "NETWORK_ERROR"
        else:
            if response.status_code < 500:
                return response, queried_at
            error = f"HTTP_{response.status_code}"
        logger.warning("%s attempt %s failed: %s", source, attempt, error)
    raise SourceUnavailable(error)
