import logging

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from checks.views import api_error

from .api_auth import authenticate_token, bearer_value

logger = logging.getLogger(__name__)

API_PREFIX = "/api/"


class ForcePasswordChangeMiddleware:
    """Send users with a one-time password to the password change page (REQ-FUNC-005)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.must_change_password:
            allowed = {
                reverse("admin:password_change"),
                reverse("admin:password_change_done"),
                reverse("admin:logout"),
            }
            if request.path not in allowed:
                return redirect("admin:password_change")
        return self.get_response(request)


class ApiTokenMiddleware:
    """Authenticate API calls that send `Authorization: Bearer <token>` and limit their rate (SCRUM-71, SCRUM-73).

    Only paths under /api/ accept tokens; a token never logs anybody into the web pages. If the header is present, it
    decides alone: a bad token is 401 even if the caller also has a web session. With a valid token, request.user is
    the token's owner and request.api_token the token; views skip the CSRF check for such calls, because a token is
    not sent automatically by a browser. Without the header nothing changes and the web session applies.

    Every answer to a valid token carries the X-RateLimit-* headers; a call over the limit gets 429 with Retry-After
    before the view runs, so nothing is checked or stored (REQ-SEC-003, UC-04 2b).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.api_token = None
        header = request.headers.get("Authorization")
        if header is None or not request.path.startswith(API_PREFIX):
            return self.get_response(request)

        try:
            value = bearer_value(header)
            authenticated = authenticate_token(value) if value else None
        except Exception:
            logger.exception("Token authentication failed")
            return api_error(500, "INTERNAL_ERROR", _("Something went wrong on our side. Please try again later."))
        if authenticated is None:
            response = api_error(401, "INVALID_TOKEN", _("The API token is missing, unknown, revoked or expired."))
            response["WWW-Authenticate"] = 'Bearer error="invalid_token"'
            return response

        token, quota = authenticated
        if quota.allowed:
            request.user = token.user
            request.api_token = token
            response = self.get_response(request)
        else:
            message = _("This token made more than %(limit)d requests in a minute. Try again in %(seconds)d s.") % {
                "limit": quota.limit,
                "seconds": quota.reset_seconds,
            }
            response = api_error(429, "RATE_LIMIT_EXCEEDED", message)
            response["Retry-After"] = str(quota.reset_seconds)
        response["X-RateLimit-Limit"] = str(quota.limit)
        response["X-RateLimit-Remaining"] = str(quota.remaining)
        response["X-RateLimit-Reset"] = str(quota.reset_seconds)
        return response
