"""Registry of all source adapters (REQ-MAINT-003): adding a source means adding one line here.

The order of ADAPTERS is the order of the checks in every response.
"""

from .registry import validate
from .vies import ViesAdapter

ADAPTERS = validate(
    [
        ViesAdapter(),
    ]
)
