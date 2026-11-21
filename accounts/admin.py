from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Organization, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "organization", "first_name", "last_name", "is_active", "is_superuser"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = [
        (None, {"fields": ["email", "password", "must_change_password"]}),
        ("Personal info", {"fields": ["first_name", "last_name"]}),
        ("Organization", {"fields": ["organization", "is_org_admin", "is_request_user", "is_review_user"]}),
        ("Permissions", {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Important dates", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [(None, {"classes": ["wide"], "fields": ["email", "password1", "password2"]})]


class VatStatusFilter(admin.SimpleListFilter):
    """Lets the operator find organizations whose VAT number VIES could not verify at registration (REQ-FUNC-004)."""

    title = "VAT number"
    parameter_name = "vat"

    def lookups(self, request, model_admin):
        return [("verified", "Verified by VIES"), ("unverified", "VAT unverified")]

    def queryset(self, request, queryset):
        if self.value() == "verified":
            return queryset.filter(vat_verified_at__isnull=False)
        if self.value() == "unverified":
            return queryset.filter(vat_verified_at__isnull=True)
        return queryset


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "vat_number", "vat_verified", "is_verified", "created_at"]
    list_filter = [VatStatusFilter]
    search_fields = ["name", "vat_number"]

    @admin.display(boolean=True, description="VAT verified", ordering="vat_verified_at")
    def vat_verified(self, organization):
        return not organization.vat_unverified
