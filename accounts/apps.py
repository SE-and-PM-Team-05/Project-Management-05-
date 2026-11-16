from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self):
        from . import backends  # noqa: F401  (connects the failed-login counter)
