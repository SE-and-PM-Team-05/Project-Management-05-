"""Checks that the adapters in the registry fit together (REQ-MAINT-003).

Runs when checks.sources is imported, so a misconfigured adapter stops the app at start-up and in CI
instead of mixing up results at run time.
"""

from .base import SourceAdapter


class RegistryError(Exception):
    """The registry contains an adapter that breaks the common interface."""


def validate(adapters):
    """Return `adapters` unchanged if they fit together; raise RegistryError otherwise.

    Each adapter must be a SourceAdapter with a non-empty, unique `source` and at least one check, and
    each check name may belong to only one adapter, so a result always maps to exactly one source.
    """
    sources = {}
    check_owners = {}
    for adapter in adapters:
        name = type(adapter).__name__
        if not isinstance(adapter, SourceAdapter):
            raise RegistryError(f"{name} is not a SourceAdapter")
        if not adapter.source:
            raise RegistryError(f"{name} has no source name")
        if adapter.source in sources:
            raise RegistryError(f"Source {adapter.source!r} is registered twice ({sources[adapter.source]}, {name})")
        sources[adapter.source] = name
        if not adapter.checks or isinstance(adapter.checks, str):
            raise RegistryError(f"{name} must list its checks as a tuple of names")
        for check in adapter.checks:
            if check in check_owners:
                raise RegistryError(f"Check {check!r} is answered by both {check_owners[check]} and {name}")
            check_owners[check] = name
    return list(adapters)
