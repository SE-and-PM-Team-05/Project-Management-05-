from django.core.management.base import BaseCommand, CommandError

from checks.models import SyncLog
from checks.sync import sync_bmf


class Command(BaseCommand):
    help = "Import the BMF list of sham companies and log the run (REQ-FUNC-070, REQ-FUNC-072)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-shrink",
            action="store_true",
            help="Accept a list with less than half the entries of the last good copy (check the feed first).",
        )

    def handle(self, *args, allow_shrink, **options):
        log = sync_bmf(allow_shrink=allow_shrink)
        if log.outcome != SyncLog.OUTCOME_SUCCESS:
            # A non-zero exit turns the GitHub Actions run red, which notifies the team.
            raise CommandError(f"BMF sync failed: {log.error_message}. The last good copy was kept.")
        self.stdout.write(
            f"BMF sync succeeded: {log.number_of_entries} entries, feed date {log.feed_timestamp:%d.%m.%Y}."
        )
