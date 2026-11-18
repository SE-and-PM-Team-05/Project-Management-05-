from django.contrib import admin

from .models import FakeCompany, SyncLog


class ReadOnlyAdmin(admin.ModelAdmin):
    """View only: these rows are written by the sync job, never by hand (REQ-FUNC-072, REQ-REL-002)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FakeCompany)
class FakeCompanyAdmin(ReadOnlyAdmin):
    list_display = ["name", "vat_number", "company_register_number", "date_listed"]
    search_fields = ["name", "vat_number", "company_register_number"]


@admin.register(SyncLog)
class SyncLogAdmin(ReadOnlyAdmin):
    list_display = ["source", "start_time", "end_time", "outcome", "number_of_entries", "feed_timestamp"]
    list_filter = ["source", "outcome"]
