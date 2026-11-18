"""REST API v1 for API tokens: GET/POST /api/v1/tokens, DELETE /api/v1/tokens/{id} (SRS 3.1.3, UC-03).

Authentication is the web session for now (REQ-INT-011); Bearer tokens follow with SCRUM-71.
"""

import json
import logging
from datetime import UTC

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt

from checks.results import format_utc
from checks.views import api_error, csrf_failure

from .models import ApiToken
from .tokens import LATEST_EXPIRY_DATE, can_manage_tokens, end_of_day, possible_owners, visible_tokens

logger = logging.getLogger(__name__)


def token_json(token):
    """Everything about a token except its value, which is never shown again after creation (REQ-FUNC-022)."""
    owner = token.user
    return {
        "id": token.pk,
        "name": token.name,
        "prefix": token.prefix,
        "owner": {"id": owner.pk, "email": owner.email, "name": owner.get_full_name() or owner.email},
        "createdAt": format_utc(token.created_at),
        "lastUsedAt": format_utc(token.last_used_at) if token.last_used_at else None,
        "expiresAt": format_utc(token.expires_at) if token.expires_at else None,
        "revokedAt": format_utc(token.revoked_at) if token.revoked_at else None,
        "active": token.is_active(),
    }


def json_api(allowed_methods):
    """Shared checks of the token endpoints: method, login, organization, CSRF, and a JSON 500 on any error."""

    def decorator(view):
        # CSRF is checked inside, after authentication, so an anonymous call gets 401 and not 403.
        @csrf_exempt
        def wrapper(request, *args, **kwargs):
            try:
                if request.method not in allowed_methods:
                    response = api_error(405, "METHOD_NOT_ALLOWED", _("Method not allowed."))
                    response["Allow"] = ", ".join(allowed_methods)
                    return response
                if not request.user.is_authenticated:
                    return api_error(401, "NOT_AUTHENTICATED", _("Log in to use the API."))
                if not can_manage_tokens(request.user):
                    return api_error(403, "PERMISSION_DENIED", _("Only users of an organization have API tokens."))
                if request.method != "GET" and csrf_failure(request):
                    return api_error(403, "CSRF_FAILED", _("Send the CSRF token in the X-CSRFToken header."))
                return view(request, *args, **kwargs)
            except Exception:
                logger.exception("Token API request failed")
                return api_error(500, "INTERNAL_ERROR", _("Something went wrong on our side. Please try again later."))

        return wrapper

    return decorator


@json_api(["GET", "POST"])
def tokens(request):
    if request.method == "GET":
        return JsonResponse({"tokens": [token_json(token) for token in visible_tokens(request.user)]})
    return create_token(request)


def create_token(request):
    """POST /api/v1/tokens: {"name": …, "userId": optional, "expiresAt": optional} → 201 with the full value once."""
    try:
        data = json.loads(request.body or b"null")
    except ValueError:  # includes UnicodeDecodeError
        return api_error(400, "INVALID_JSON", _("The request body is not valid JSON."))
    if not isinstance(data, dict):
        return api_error(400, "INVALID_INPUT", _("Send a JSON object."))

    errors = {}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors["name"] = [_("Give the token a name.")]
    elif len(name.strip()) > 100:
        errors["name"] = [_("At most 100 characters.")]

    owner = request.user
    user_id = data.get("userId")
    if user_id is not None and user_id != request.user.pk:
        if not request.user.is_org_admin:
            # Only an Org Admin may create tokens for other users (SRS Appendix A).
            return api_error(403, "PERMISSION_DENIED", _("Only an Org Admin can create tokens for other users."))
        owner = possible_owners(request.user).filter(pk=user_id).first() if type(user_id) is int else None
        if owner is None:
            errors["userId"] = [_("No active user with this ID in your organization.")]

    expires_at = data.get("expiresAt")
    if expires_at is not None:
        try:
            expires_at = parse_expiry(expires_at)
        except ValueError as error:
            errors["expiresAt"] = [str(error)]
        else:
            if expires_at <= timezone.now():
                errors["expiresAt"] = [_("The expiry must be in the future.")]

    if errors:
        return api_error(400, "INVALID_INPUT", _("Some fields are invalid."), errors)

    token, value = ApiToken.issue(owner, name.strip(), created_by=request.user, expires_at=expires_at)
    body = token_json(token)
    body["token"] = value  # the only time the full value leaves the server (REQ-FUNC-022)
    response = JsonResponse(body, status=201)
    response["Cache-Control"] = "no-store"
    return response


def parse_expiry(value):
    """Turn expiresAt into an aware datetime, or raise ValueError with the message for the client.

    A date means the end of that day (Vienna time); a date and time without offset is read as UTC.
    """
    invalid = ValueError(_("Use an ISO 8601 date or date and time."))
    if not isinstance(value, str):
        raise invalid
    try:
        day = parse_date(value)
        moment = None if day else parse_datetime(value)
    except ValueError:
        raise invalid from None
    if day is None and moment is None:
        raise invalid
    if (day or moment.date()) > LATEST_EXPIRY_DATE:
        raise ValueError(_("The expiry must be in %(year)s or earlier.") % {"year": LATEST_EXPIRY_DATE.year})
    if day:
        return end_of_day(day)
    return moment if timezone.is_aware(moment) else moment.replace(tzinfo=UTC)


@json_api(["DELETE"])
def revoke_token(request, token_id):
    """DELETE /api/v1/tokens/{id}: revoke a token; 404 for tokens the caller may not see (REQ-FUNC-013)."""
    token = visible_tokens(request.user).filter(pk=token_id).first()
    if token is None:
        return api_error(404, "NOT_FOUND", _("Token not found."))
    token.revoke()
    return HttpResponse(status=204)
