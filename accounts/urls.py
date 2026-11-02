from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/done/", views.register_done, name="register_done"),
    path("verify/resend/", views.resend_verification, name="resend_verification"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("terms/", TemplateView.as_view(template_name="accounts/terms.html"), name="terms"),
    # Minimal login so the landing page button works; SCRUM-22 adds lockout, reset and session rules.
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
