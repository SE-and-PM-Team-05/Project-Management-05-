"""Registry of all source adapters (REQ-MAINT-003): adding a source means adding one line here."""

from .vies import ViesAdapter

ADAPTERS = [
    ViesAdapter(),
]
