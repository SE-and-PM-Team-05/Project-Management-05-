import pytest


@pytest.fixture(autouse=True)
def test_settings(settings):
    # Tests run without collectstatic, so skip the hashed-file manifest.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    # The test client speaks plain HTTP; the HTTPS redirect is covered by `check --deploy` in CI.
    settings.SECURE_SSL_REDIRECT = False
