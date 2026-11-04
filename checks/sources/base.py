"""The common interface of all source adapters (REQ-MAINT-003)."""


class SourceAdapter:
    """One external data source, e.g. VIES.

    An adapter answers one or more checks from a single source. It must not import Django, so it can
    be used and tested without the web app. Register new adapters in checks/sources/__init__.py.
    """

    #: Name reported as "source" in every result, e.g. "VIES".
    source = ""
    #: Names of the checks this adapter answers, e.g. ("vatValid", "nameMatchesVat").
    checks = ()

    def applies_to(self, partner):
        """Whether the source is asked at all; otherwise its checks are NOT_APPLICABLE (REQ-FUNC-038)."""
        return True

    def run(self, partner, deadline):
        """Return one CheckResult per name in `checks`.

        `deadline` is a time.monotonic() value; the adapter must give up by then (REQ-INT-013). An
        unavailable source is reported as UNKNOWN / SOURCE_UNAVAILABLE, never raised.
        """
        raise NotImplementedError
