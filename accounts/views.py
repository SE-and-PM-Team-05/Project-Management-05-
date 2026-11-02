import hashlib
import secrets

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AcceptInvitationForm,
    InvitationForm,
    MemberEditForm,
    RegistrationForm,
    ResendVerificationForm,
)
from .models import Invitation, User
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

@login_required
def team_members(request):
    if not request.user.is_org_admin:
        return HttpResponseForbidden("Only Organization Admins can manage team members.")

    members = User.objects.filter(
        organization=request.user.organization
    ).order_by("first_name", "last_name")

    return render(
        request,
        "accounts/team_members.html",
        {"members": members},
    )


@login_required
@transaction.atomic
def invite_member(request):
    if not request.user.is_org_admin or request.user.organization is None:
        return HttpResponseForbidden(
            "Only Organization Admins can invite team members."
        )

    form = InvitationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip()

        if User.objects.filter(email__iexact=email).exists():
            form.add_error(
                "email",
                "A user with this email address already exists."
            )

        elif Invitation.objects.filter(
            organization=request.user.organization,
            email__iexact=email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            form.add_error(
                "email",
                "A pending invitation already exists for this email address."
            )

        else:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()

            invitation = Invitation.objects.create(
                organization=request.user.organization,
                email=email,
                token_hash=token_hash,
                is_org_admin=form.cleaned_data["is_org_admin"],
                is_request_user=form.cleaned_data["is_request_user"],
                is_review_user=form.cleaned_data["is_review_user"],
            )

            invitation_url = request.build_absolute_uri(
                reverse("accept_invitation", args=[token])
            )

            send_mail(
                subject="Invitation to BizPartnerCheck",
                message=(
                    f"You have been invited to join "
                    f"{invitation.organization.name} on BizPartnerCheck.\n\n"
                    f"Accept your invitation here:\n{invitation_url}\n\n"
                    "This invitation expires in 7 days."
                ),
                from_email=None,
                recipient_list=[email],
                fail_silently=False,
            )

            return redirect("team_members")

    return render(
        request,
        "accounts/invite_member.html",
        {"form": form},
    )


def accept_invitation(request, token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    with transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update()
            .select_related("organization")
            .filter(token_hash=token_hash)
            .first()
        )

        if invitation is None or not invitation.is_valid():
            return render(
                request,
                "accounts/invitation_invalid.html",
                status=400,
            )

        form = AcceptInvitationForm(request.POST or None)

        if request.method == "POST" and form.is_valid():
            if User.objects.filter(email__iexact=invitation.email).exists():
                form.add_error(
                    None,
                    "An account with this email address already exists.",
                )
            else:
                data = form.cleaned_data

                User.objects.create_user(
                    email=invitation.email,
                    password=data["password1"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    organization=invitation.organization,
                    is_active=True,
                    is_org_admin=invitation.is_org_admin,
                    is_request_user=invitation.is_request_user,
                    is_review_user=invitation.is_review_user,
                )

                invitation.accepted_at = timezone.now()
                invitation.save(update_fields=["accepted_at"])

                return render(
                    request,
                    "accounts/invitation_accepted.html",
                )

    return render(
        request,
        "accounts/accept_invitation.html",
        {"form": form},
    )

@login_required
@transaction.atomic
def edit_member(request, member_id):
    if not request.user.is_org_admin or request.user.organization is None:
        return HttpResponseForbidden("Only Organization Admins can edit team members.")

    member = get_object_or_404(
        User.objects.select_for_update(),
        pk=member_id,
        organization=request.user.organization,
    )

    initial_data = {
        "first_name": member.first_name,
        "last_name": member.last_name,
        "is_org_admin": member.is_org_admin,
        "is_request_user": member.is_request_user,
        "is_review_user": member.is_review_user,
    }

    form = MemberEditForm(request.POST or None, initial=initial_data)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data

        protected_roles = [
            ("is_org_admin", "Org Admin"),
            ("is_review_user", "Review User"),
        ]

        for role_field, role_name in protected_roles:
            if (
                member.is_active
                and getattr(member, role_field)
                and not data[role_field]
            ):
                remaining = User.objects.filter(
                    organization=request.user.organization,
                    is_active=True,
                    **{role_field: True},
                ).exclude(pk=member.pk).count()

                if remaining == 0:
                    return HttpResponseForbidden(
                        f"You cannot remove the last active {role_name}."
                    )

        member.first_name = data["first_name"]
        member.last_name = data["last_name"]
        member.is_org_admin = data["is_org_admin"]
        member.is_request_user = data["is_request_user"]
        member.is_review_user = data["is_review_user"]

        member.save()

        return redirect("team_members")

    return render(
        request,
        "accounts/edit_member.html",
        {"form": form, "member": member},
    )

@login_required
@transaction.atomic
def deactivate_member(request, member_id):
    if not request.user.is_org_admin or request.user.organization is None:
        return HttpResponseForbidden(
            "Only Organization Admins can deactivate team members."
        )

    if request.method != "POST":
        return HttpResponseForbidden("Deactivation requires a POST request.")

    member = get_object_or_404(
        User.objects.select_for_update(),
        pk=member_id,
        organization=request.user.organization,
    )

    if member.is_active:
        protected_roles = [
            ("is_org_admin", "Org Admin"),
            ("is_review_user", "Review User"),
        ]

        for role_field, role_name in protected_roles:
            if getattr(member, role_field):
                remaining = User.objects.filter(
                    organization=request.user.organization,
                    is_active=True,
                    **{role_field: True},
                ).exclude(pk=member.pk).count()

                if remaining == 0:
                    return HttpResponseForbidden(
                        f"You cannot deactivate the last active {role_name}."
                    )

        member.is_active = False
        member.save(update_fields=["is_active"])

    return redirect("team_members")

@login_required
@transaction.atomic
def reactivate_member(request, member_id):
    if not request.user.is_org_admin or request.user.organization is None:
        return HttpResponseForbidden(
            "Only Organization Admins can reactivate team members."
        )

    if request.method != "POST":
        return HttpResponseForbidden("Reactivation requires a POST request.")

    member = get_object_or_404(
        User.objects.select_for_update(),
        pk=member_id,
        organization=request.user.organization,
    )

    member.is_active = True
    member.save(update_fields=["is_active"])

    return redirect("team_members")

@login_required
@transaction.atomic
def delete_member(request, member_id):
    if not request.user.is_org_admin or request.user.organization is None:
        return HttpResponseForbidden(
            "Only Organization Admins can delete team members."
        )

    if request.method != "POST":
        return HttpResponseForbidden("Deletion requires a POST request.")

    member = get_object_or_404(
        User.objects.select_for_update(),
        pk=member_id,
        organization=request.user.organization,
    )

    if member.is_active:
        protected_roles = [
            ("is_org_admin", "Org Admin"),
            ("is_review_user", "Review User"),
        ]

        for role_field, role_name in protected_roles:
            if getattr(member, role_field):
                remaining = User.objects.filter(
                    organization=request.user.organization,
                    is_active=True,
                    **{role_field: True},
                ).exclude(pk=member.pk).count()

                if remaining == 0:
                    return HttpResponseForbidden(
                        f"You cannot delete the last active {role_name}."
                    )

    member.delete()

    return redirect("team_members")