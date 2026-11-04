from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from . import views
from .forms import LoginForm

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/done/", views.register_done, name="register_done"),
    path("verify/resend/", views.resend_verification, name="resend_verification"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("terms/", TemplateView.as_view(template_name="accounts/terms.html"), name="terms"),
    path("team/", views.team_members, name="team_members"),
    path("team/invite/", views.invite_member, name="invite_member"),
    path("team/accept/<str:token>/", views.accept_invitation, name="accept_invitation"),
    path("team/edit/<int:member_id>/", views.edit_member, name="edit_member"),
    path(
        "team/deactivate/<int:member_id>/",
        views.deactivate_member,
        name="deactivate_member",
    ),
    path(
        "team/reactivate/<int:member_id>/",
        views.reactivate_member,
        name="reactivate_member",
    ),
    path(
        "team/delete/<int:member_id>/",
        views.delete_member,
        name="delete_member",
    ),
    # Login, logout and password reset are Django's built-in views (REQ-FUNC-003); lockout is in LoginForm and
    # accounts.backends (REQ-SEC-004).
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html", authentication_form=LoginForm),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
]
