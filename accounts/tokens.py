"""Who may see, create and revoke which API tokens (SRS Appendix A, REQ-FUNC-020, REQ-FUNC-023).

Shared by the web page (accounts/views_tokens.py) and the API (accounts/api.py), so both follow the same rules:
every user of an organization manages their own tokens, an Org Admin manages all tokens of the organization.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import ApiToken, User


def can_manage_tokens(user):
    """The Super Admin has no organization and therefore no tokens."""
    return user.is_authenticated and user.organization_id is not None


def visible_tokens(user):
    """Tokens the user may list and revoke; always scoped to the user's organization (REQ-FUNC-013)."""
    tokens = ApiToken.objects.select_related("user").filter(user__organization_id=user.organization_id)
    if not user.is_org_admin:
        tokens = tokens.filter(user=user)
    return tokens


def possible_owners(user):
    """Users the given user may create a token for: everyone active in the organization for an Org Admin."""
    if user.is_org_admin:
        return User.objects.filter(organization_id=user.organization_id, is_active=True).order_by("email")
    return User.objects.filter(pk=user.pk)


def end_of_day(day):
    """An expiry date means the token works until the end of that day, Vienna time."""
    return timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
