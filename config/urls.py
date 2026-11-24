from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import TemplateView

from checks.views import check_form


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("healthz", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("checks/new", check_form, name="check_form"),
    path("api/v1/", include("checks.urls")),
    path("api/v1/", include("accounts.api_urls")),
    path("", include("accounts.urls")),
]
