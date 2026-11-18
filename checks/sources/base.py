"""The common interface of all source adapters (REQ-MAINT-003).

Plain Python without Django, so an adapter can be used and tested without the web app. The exception is a
list-based source such as BMF, which reads the list the daily sync stored in the database.
"""

from ..results import SOURCE_UNAVAILABLE, UNKNOWN, CheckResult, utc_now


class SourceAdapter:
    """One external data source, e.g. VIES, the BMF list or the HFU list.

    To add a source, write a subclass in its own module under checks/sources/ and add one instance to
    ADAPTERS in checks/sources/__init__.py. Nothing else changes: the runner, the API and the other
    adapters only know this interface. See "Adding a data source" in README.md.
    """

    #: Name reported as "source" in every result, e.g. "VIES". Unique across the registry.
    source = ""
    #: Names of the checks this adapter answers, e.g. ("vatValid", "nameMatchesVat"). Each check name
    #: belongs to exactly one adapter.
    checks = ()

    def applies_to(self, partner):
        """Whether the source is asked at all; otherwise its checks are NOT_APPLICABLE (REQ-FUNC-038)."""
        return True

    def run(self, partner, deadline):
        """Return one CheckResult per name in `checks`.

            `deadline` is a time.monotonic() value; the adapter must give up by then (REQ-INT-013). An
            unavailable source is reported as UNKNOWN / SOURCE_UNAVAILABLE (see `unavailable`), never raised.
            The runner still guards against adapters that raise, overrun or return the wrong checks, without
        calling adapter code for that.
        """
        raise NotImplementedError

    # Helpers, so every adapter reports results the same way.

    def result(self, check, value, data_timestamp, reason=None, details=None):
        """A CheckResult of this source."""
        return CheckResult(check, value, self.source, data_timestamp, reason=reason, details=details or {})

    def unknown(self, check, reason, data_timestamp=None, details=None):
        """UNKNOWN for one check, with a reason such as NO_DETAILS_FOUND."""
        return self.result(check, UNKNOWN, data_timestamp or utc_now(), reason=reason, details=details)

    def unavailable(self, error_code=None, data_timestamp=None):
        """UNKNOWN / SOURCE_UNAVAILABLE for all checks of this source, e.g. after a timeout.

        `error_code` is a short, language-neutral reason (e.g. "TIMEOUT") stored in the details.
        """
        details = {"error": error_code} if error_code else {}
        moment = data_timestamp or utc_now()
        return [self.unknown(name, SOURCE_UNAVAILABLE, moment, details) for name in self.checks]
