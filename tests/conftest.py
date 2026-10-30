import pytest


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    # Tests run without collectstatic, so skip the hashed-file manifest.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
