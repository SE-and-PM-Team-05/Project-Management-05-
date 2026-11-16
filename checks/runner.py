"""Runs all source adapters for one partner, in parallel and within the time budget."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait

from .results import NOT_APPLICABLE, SOURCE_UNAVAILABLE, UNKNOWN, CheckResult, utc_now
from .sources import ADAPTERS

logger = logging.getLogger(__name__)

# Maximum seconds per source and check request, including one retry (REQ-INT-013, REQ-REL-003).
SOURCE_TIME_BUDGET = 8.0


def run_checks(partner, adapters=None):
    """Return the results of all checks, in registry order.

    Sources run in parallel and independently (REQ-FUNC-039): a source that fails, raises or is still
    running when the budget is over only turns its own checks into UNKNOWN / SOURCE_UNAVAILABLE
    (REQ-REL-001), and the caller always gets an answer within the budget.
    """
    adapters = ADAPTERS if adapters is None else adapters
    deadline = time.monotonic() + SOURCE_TIME_BUDGET
    started_at = utc_now()

    applicable = [a for a in adapters if a.applies_to(partner)]
    executor = ThreadPoolExecutor(max_workers=max(len(applicable), 1), thread_name_prefix="source")
    futures = {adapter: executor.submit(adapter.run, partner, deadline) for adapter in applicable}
    wait(futures.values(), timeout=max(deadline - time.monotonic(), 0))
    # Don't wait for a source that overran its budget; its thread ends on its own.
    executor.shutdown(wait=False, cancel_futures=True)

    results = []
    for adapter in adapters:
        future = futures.get(adapter)
        if future is None:
            results += [CheckResult(name, NOT_APPLICABLE, adapter.source) for name in adapter.checks]
        elif future.done() and future.exception() is None:
            results += future.result()
        else:
            if future.done():
                logger.error("Source %s failed", adapter.source, exc_info=future.exception())
            else:
                logger.warning("Source %s exceeded the %s s budget", adapter.source, SOURCE_TIME_BUDGET)
            results += [
                CheckResult(name, UNKNOWN, adapter.source, started_at, reason=SOURCE_UNAVAILABLE)
                for name in adapter.checks
            ]
    return results
