from django.urls import path

from . import api

urlpatterns = [
    path("tokens", api.tokens, name="api_v1_tokens"),
    path("tokens/<int:token_id>", api.revoke_token, name="api_v1_revoke_token"),
]
