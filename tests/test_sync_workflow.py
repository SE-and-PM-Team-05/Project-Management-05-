"""SCRUM-64: the daily sync job must be able to load the Django settings.

The job runs `python manage.py sync_bmf` with only the variables in .github/workflows/sync-bmf.yml and debug off.
If a setting becomes required (as KEYCLOAK_CLIENT_SECRET did with SCRUM-76), the job would crash on every run before
writing a sync log row, and the normal CI would not notice, because it sets its own variables. These tests load the
settings in a fresh process with exactly the workflow's variables.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
WORKFLOW = BASE_DIR / ".github" / "workflows" / "sync-bmf.yml"
# Placeholder for the repository secret; the settings only parse it, they don't connect.
SECRET_PLACEHOLDER = "postgres://sync:sync@localhost:5432/bizpartnercheck"


def workflow_env():
    """The KEY: value pairs of the job's env blocks, with ${{ secrets.… }} replaced by a placeholder."""
    env = {}
    for key, value in re.findall(r"^\s+([A-Z][A-Z0-9_]*):\s*(\S.*?)\s*$", WORKFLOW.read_text(), re.MULTILINE):
        env[key] = SECRET_PLACEHOLDER if value.startswith("${{") else value.strip("\"'")
    return env


def load_settings(env):
    """Import the settings in a new process, as `manage.py` would in the job; returns the finished process."""
    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        # Windows: Python needs SYSTEMROOT to start its socket support (WinError 10106 without it).
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "DJANGO_SETTINGS_MODULE": "config.settings",
        # The job does not set DJANGO_DEBUG, so debug is off; set it explicitly so a local .env cannot turn it on.
        "DJANGO_DEBUG": "false",
        **env,
    }
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=BASE_DIR,
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_workflow_sets_the_variables_the_settings_need():
    """Verifies REQ-FUNC-070, REQ-INST-001."""
    env = workflow_env()
    assert {"DATABASE_URL", "DJANGO_SECRET_KEY", "KEYCLOAK_CLIENT_SECRET"} <= set(env)

    result = load_settings(env)

    assert result.returncode == 0, result.stderr


@pytest.mark.skipif((BASE_DIR / ".env").exists(), reason="a local .env may fill in the missing variable")
def test_settings_refuse_to_load_without_the_keycloak_secret():
    # Shows that the test above would notice a missing variable.
    """Verifies REQ-INST-001."""
    env = {key: value for key, value in workflow_env().items() if key != "KEYCLOAK_CLIENT_SECRET"}

    result = load_settings(env)

    assert result.returncode != 0
    assert "KEYCLOAK_CLIENT_SECRET must be set" in result.stderr


def test_workflow_only_reads_the_repository():
    """Verifies REQ-FUNC-070."""
    assert re.search(r"^permissions:\s*\n\s+contents: read\s*$", WORKFLOW.read_text(), re.MULTILINE)
