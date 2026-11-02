from django.shortcuts import redirect
from django.urls import reverse


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
