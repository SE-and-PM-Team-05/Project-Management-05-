"""REST API v1 for partner checks (REQ-INT-010)."""

import json
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.csrf import csrf_exempt

from .forms import parse_check_input
from .models import CheckRequest, CheckRequestResult
from .results import utc_now
from .runner import run_checks

logger = logging.getLogger(__name__)

DISCLAIMER = gettext_lazy(
    "Informational only; source data is not guaranteed complete or current. BizPartnerCheck carries no "
    "liability; the contracting decision remains with the customer."
)


def api_error(status, code, message, fields=None):
    """JSON error body with a stable, language-neutral code and a translated message (REQ-INT-012)."""
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return JsonResponse({"error": error}, status=status)


def csrf_failure(request):
    """Run Django's CSRF check by hand, so a failure gets a JSON body instead of an HTML page."""
    return CsrfViewMiddleware(lambda r: None).process_view(request, None, (), {})


# CSRF is checked inside the view, after authentication, so an anonymous call gets 401 and not 403.
@csrf_exempt
def create_check(request):
    """Return a JSON 500 instead of Django's HTML error page if anything unexpected fails (REQ-INT-012)."""
    try:
        return _create_check(request)
    except Exception:
        logger.exception("Check request failed")
        return api_error(500, "INTERNAL_ERROR", _("Something went wrong on our side. Please try again later."))


def _create_check(request):
    """POST /api/v1/checks: run the VIES checks for one partner and return the result (UC-04).

    Authentication is the web session for now (REQ-INT-011); API tokens follow with SCRUM-48. Every accepted
    request is stored as evidence before the response is sent (REQ-REL-004).
    """
    received_at = utc_now()
    if request.method != "POST":
        response = api_error(405, "METHOD_NOT_ALLOWED", _("Use POST to start a check."))
        response["Allow"] = "POST"
        return response
    user = request.user
    if not user.is_authenticated:
        return api_error(401, "NOT_AUTHENTICATED", _("Log in to use the API."))
    # Only Request Users of an organization may start a check (SRS Appendix A, REQ-FUNC-012).
    if not (user.is_request_user and user.organization_id):
        return api_error(403, "PERMISSION_DENIED", _("You need the Request User role to start a check."))
    if csrf_failure(request):
        return api_error(403, "CSRF_FAILED", _("Send the CSRF token in the X-CSRFToken header."))

    try:
        data = json.loads(request.body or b"null")
    except ValueError:  # includes UnicodeDecodeError
        return api_error(400, "INVALID_JSON", _("The request body is not valid JSON."))
    try:
        partner, reference = parse_check_input(data)
    except ValidationError as error:
        # Invalid input is rejected before any source is called (REQ-FUNC-030).
        return api_error(400, "INVALID_INPUT", _("Some fields are invalid."), error.message_dict)

    checks = run_checks(partner)
    check_request = store_check_request(user, partner, reference, checks, received_at)

    # Response shape of SRS Appendix B (REQ-FUNC-045); only the checks implemented so far are listed.
    body = check_request.to_json()
    body["disclaimer"] = str(DISCLAIMER)  # REQ-FUNC-048
    return JsonResponse(body, status=200)


def store_check_request(user, partner, reference, checks, received_at):
    """Store the request with all its results, or nothing (REQ-REL-004, REQ-FUNC-041).

    A database error propagates, so the caller answers with 500 and no partial record remains. The sources
    are queried before the transaction starts, so it stays short.
    """
    with transaction.atomic():
        check_request = CheckRequest.objects.create(
            organization=user.organization,
            requested_by=user,
            requested_by_name=user.get_full_name() or user.email,
            # Called through the API with a web session until API tokens exist (SCRUM-48).
            channel=CheckRequest.CHANNEL_API,
            vat_number=partner.vat_number,
            company_name=partner.company_name,
            company_register_number=partner.company_register_number,
            address=partner.address,
            required_license_codes=list(partner.required_license_codes),
            reference=reference,
            received_at=received_at,
            completed_at=utc_now(),
        )
        CheckRequestResult.objects.bulk_create(
            CheckRequestResult(
                request=check_request,
                position=position,
                check_name=result.check,
                result=result.result,
                reason=result.reason or "",
                source=result.source,
                data_timestamp=result.data_timestamp,
                details=result.details,
            )
            for position, result in enumerate(checks)
        )
    return check_request
