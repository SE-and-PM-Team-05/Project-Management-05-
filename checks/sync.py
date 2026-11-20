"""Daily import of the BMF list of sham companies (REQ-FUNC-070, REQ-FUNC-072, REQ-FUNC-073, REQ-REL-002).

`python manage.py sync_bmf` runs it; GitHub Actions starts that once a day (.github/workflows/sync-bmf.yml).
Every run writes one SyncLog row, successful or not. The list is replaced as a whole in one transaction,
together with the success row, so a check sees either the old list with its old sync time or the new list
with the new one. A failed run changes nothing but adds its failed row: the last good copy stays.
"""

import logging

from django.db import transaction

from .models import FakeCompany, SyncLog
from .results import utc_now
from .sources import bmf_feed

logger = logging.getLogger(__name__)

# A new list with fewer than half the entries of the last good copy is treated as a broken download, not
# as BMF removing half the list; `allow_shrink` overrides this once a person has checked the feed.
MIN_SHARE_OF_LAST_COPY = 0.5


def sync_bmf(download=bmf_feed.download, allow_shrink=False):
    """Run one sync and return its SyncLog row; never raises for a feed problem, it logs it instead."""
    start_time = utc_now()
    feed = None
    try:
        feed = bmf_feed.parse(download())
        if not allow_shrink:
            _check_not_shrunk(len(feed.entries))
        with transaction.atomic():
            FakeCompany.objects.all().delete()
            FakeCompany.objects.bulk_create(
                FakeCompany(
                    name=entry.name,
                    vat_number=entry.vat_number,
                    company_register_number=entry.company_register_number,
                    address=entry.address,
                    date_listed=entry.date_listed,
                )
                for entry in feed.entries
            )
            # Inside the transaction, so the success row and the new list become visible together and
            # end_time is only written once the list is fully stored (REQ-FUNC-073 stale flag).
            return SyncLog.objects.create(
                source=SyncLog.SOURCE_BMF,
                start_time=start_time,
                end_time=utc_now(),
                outcome=SyncLog.OUTCOME_SUCCESS,
                number_of_entries=len(feed.entries),
                feed_timestamp=feed.build_date,
            )
    except Exception as error:  # Every failure must end in a log row, whatever its cause (REQ-FUNC-072).
        logger.exception("BMF sync failed")
        return SyncLog.objects.create(
            source=SyncLog.SOURCE_BMF,
            start_time=start_time,
            end_time=utc_now(),
            outcome=SyncLog.OUTCOME_FAILED,
            feed_timestamp=feed.build_date if feed else None,
            error_message=_describe(error),
        )


def _check_not_shrunk(number_of_entries):
    last = SyncLog.last_success(SyncLog.SOURCE_BMF)
    if last and number_of_entries < last.number_of_entries * MIN_SHARE_OF_LAST_COPY:
        raise bmf_feed.FeedError(
            "TOO_FEW_ENTRIES", f"{number_of_entries} entries, the last good copy has {last.number_of_entries}"
        )


def _describe(error):
    """The error for the sync log: the feed's own code first, e.g. "HTTP_503", else the exception's type."""
    if isinstance(error, bmf_feed.FeedError):
        return str(error)
    return f"{type(error).__name__}: {error}"[:2000]
