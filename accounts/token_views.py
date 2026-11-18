"""Web page for API tokens (UC-03): list, create and revoke, with the same rules as the API (accounts/tokens.py)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .forms import ApiTokenForm
from .models import ApiToken
from .tokens import can_manage_tokens, end_of_day, possible_owners, visible_tokens


@login_required
def api_tokens(request):
    if not can_manage_tokens(request.user):
        return HttpResponseForbidden(_("Only users of an organization have API tokens."))

    owners = possible_owners(request.user)
    form = ApiTokenForm(request.POST or None, owners=owners, initial={"owner": request.user})
    new_token = new_value = None

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        expires_at = end_of_day(data["expires_on"]) if data["expires_on"] else None
        new_token, new_value = ApiToken.issue(
            data["owner"], data["name"], created_by=request.user, expires_at=expires_at
        )
        form = ApiTokenForm(owners=owners, initial={"owner": request.user})

    response = render(
        request,
        "accounts/api_tokens.html",
        {
            "form": form,
            "tokens": visible_tokens(request.user),
            "show_owner": request.user.is_org_admin,
            # Rendered into this one response only; it is not stored and cannot be shown again (REQ-FUNC-022).
            "new_token": new_token,
            "new_value": new_value,
        },
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
def revoke_api_token(request, token_id):
    if not can_manage_tokens(request.user):
        return HttpResponseForbidden(_("Only users of an organization have API tokens."))
    token = visible_tokens(request.user).filter(pk=token_id).first()
    if token is None:
        raise Http404
    token.revoke()
    messages.success(
        request, _("Token “%(name)s” revoked. Calls with it are rejected from now on.") % {"name": token.name}
    )
    return redirect("api_tokens")
