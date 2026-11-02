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


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "vat_number", "is_verified", "created_at"]
    search_fields = ["name", "vat_number"]
