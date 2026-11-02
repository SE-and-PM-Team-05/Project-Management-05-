"""Email verification links for new organizations (REQ-FUNC-002)."""

from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

LINK_MAX_AGE = 24 * 60 * 60  # seconds
SALT = "accounts.verify-email"


def make_token(user):
    return signing.dumps(user.pk, salt=SALT)


def read_token(token):
    """Return the user id in the token; raises signing.SignatureExpired or signing.BadSignature."""
    return signing.loads(token, salt=SALT, max_age=LINK_MAX_AGE)


def send_verification_email(request, user):
    link = request.build_absolute_uri(reverse("verify_email", args=[make_token(user)]))
    body = render_to_string("accounts/verification_email.txt", {"user": user, "link": link})
    send_mail("Confirm your BizPartnerCheck registration", body, None, [user.email])
