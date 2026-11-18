from django.urls import path
from django.views.generic import TemplateView

from . import token_views, views

urlpatterns = [
    path("register/", views.register, name="register"),
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
    path("tokens/", token_views.api_tokens, name="api_tokens"),
    path("tokens/<int:token_id>/revoke/", token_views.revoke_api_token, name="revoke_api_token"),
]
