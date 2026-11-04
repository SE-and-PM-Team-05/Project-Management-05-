from django.urls import path

from . import views

urlpatterns = [
    path("checks", views.create_check, name="api_create_check"),
]
