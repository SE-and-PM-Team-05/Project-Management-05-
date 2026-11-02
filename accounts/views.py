from django.core import signing
from django.shortcuts import redirect, render

from .forms import RegistrationForm, ResendVerificationForm
from .models import User
from .verification import read_token, send_verification_email


def register(request):
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        send_verification_email(request, user)
        return redirect("register_done")
    return render(request, "accounts/register.html", {"form": form})


def register_done(request):
    return render(request, "accounts/register_done.html")


def verify_email(request, token):
    try:
        user_id = read_token(token)
    except signing.SignatureExpired:
        return render(request, "accounts/verify_failed.html", {"expired": True}, status=400)
    except signing.BadSignature:
        return render(request, "accounts/verify_failed.html", {"expired": False}, status=400)

    user = User.objects.select_related("organization").filter(pk=user_id, organization__isnull=False).first()
    if user is None:
        return render(request, "accounts/verify_failed.html", {"expired": False}, status=400)
    if not user.organization.is_verified:
        user.organization.is_verified = True
        user.organization.save(update_fields=["is_verified"])
        user.is_active = True
        user.save(update_fields=["is_active"])
    return render(request, "accounts/verify_done.html")


def resend_verification(request):
    form = ResendVerificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(
            email__iexact=form.cleaned_data["email"], organization__is_verified=False, is_org_admin=True
        ).first()
        if user:
            send_verification_email(request, user)
        # Same answer whether or not the address is registered, so nobody can probe for accounts.
        return render(request, "accounts/resend_done.html")
    return render(request, "accounts/resend.html", {"form": form})
