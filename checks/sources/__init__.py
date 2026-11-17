"""Registry of all source adapters (REQ-MAINT-003): adding a source means adding one line here."""

from .hfu import HfuAdapter
from .vies import ViesAdapter

ADAPTERS = [
    ViesAdapter(),
    HfuAdapter(),
]
