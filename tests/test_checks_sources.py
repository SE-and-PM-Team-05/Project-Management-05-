"""The common adapter interface and registry of the data sources (SCRUM-59, REQ-MAINT-003, REQ-INT-013)."""

import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from checks import runner
from checks.results import FALSE, TRUE, CheckResult, Partner, utc_now
from checks.sources import ADAPTERS
from checks.sources.base import SourceAdapter
from checks.sources.registry import RegistryError, validate
from checks.sources.vies import ViesAdapter

PARTNER = Partner(vat_number="ATU12345678", company_name="Muster Bau GmbH")
REPO_ROOT = Path(__file__).resolve().parent.parent


class ListedAdapter(SourceAdapter):
    """A test source: a made-up blacklist that only needs this class to be added."""

    source = "TEST_LIST"
    checks = ("onTestList",)

    def run(self, partner, deadline):
        return [self.result("onTestList", FALSE, utc_now())]


def adapter(source, checks, run=None):
    """A SourceAdapter instance with the given source name, checks and run() behaviour."""
    attrs = {"source": source, "checks": checks}
    if run:
        attrs["run"] = run
    return type(f"{source.title()}Adapter", (SourceAdapter,), attrs)()


# --- Registry ---


def test_req_maint_003_registry_holds_the_vies_adapter():
    assert any(isinstance(a, ViesAdapter) for a in ADAPTERS)
    assert validate(ADAPTERS) == ADAPTERS


def test_req_maint_003_adding_a_test_source_needs_only_its_module_and_the_registry():
    """Acceptance test of REQ-MAINT-003: the runner and VIES stay as they are."""
    registry = validate([ViesAdapter(), ListedAdapter()])
    with mock.patch(
        "checks.sources.vies.query_vies", return_value=({"valid": True, "name": "Muster Bau GmbH"}, utc_now())
    ):
        results = runner.run_checks(PARTNER, adapters=registry)
    assert [(r.check, r.result, r.source) for r in results] == [
        ("vatValid", TRUE, "VIES"),
        ("nameMatchesVat", TRUE, "VIES"),
        ("onTestList", FALSE, "TEST_LIST"),
    ]


def test_req_maint_003_same_source_twice_is_rejected():
    with pytest.raises(RegistryError, match="registered twice"):
        validate([adapter("A", ("one",)), adapter("A", ("two",))])


def test_req_maint_003_check_answered_by_two_sources_is_rejected():
    with pytest.raises(RegistryError, match="answered by both"):
        validate([adapter("A", ("vatValid",)), adapter("B", ("vatValid",))])


@pytest.mark.parametrize(
    "bad",
    [adapter("", ("one",)), adapter("A", ()), adapter("A", "one"), object()],
    ids=["no source name", "no checks", "checks as a string", "not an adapter"],
)
def test_req_maint_003_adapter_breaking_the_interface_is_rejected(bad):
    with pytest.raises(RegistryError):
        validate([bad])


def test_req_maint_003_adapters_work_without_django():
    """Importing and running the adapters must not load Django (REQ-MAINT-003)."""
    code = (
        "import sys, time\n"
        "from checks.results import Partner\n"
        "from checks.sources import ADAPTERS\n"
        "assert ADAPTERS\n"
        "assert not [m for m in sys.modules if m == 'django' or m.startswith('django.')], 'Django was imported'\n"
    )
    subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, check=True)


# --- Helpers of the interface ---


def test_unavailable_reports_every_check_of_the_source():
    results = adapter("A", ("one", "two")).unavailable("TIMEOUT")
    assert [(r.check, r.result, r.reason, r.source, r.details) for r in results] == [
        ("one", "UNKNOWN", "SOURCE_UNAVAILABLE", "A", {"error": "TIMEOUT"}),
        ("two", "UNKNOWN", "SOURCE_UNAVAILABLE", "A", {"error": "TIMEOUT"}),
    ]
    assert all(r.data_timestamp for r in results)


def test_base_run_must_be_implemented():
    with pytest.raises(NotImplementedError):
        SourceAdapter().run(PARTNER, time.monotonic() + 1)


# --- The runner holds each adapter to its declared checks ---


def test_req_func_039_missing_result_becomes_unknown():
    lazy = adapter("A", ("one", "two"), run=lambda self, p, d: [self.result("one", TRUE, utc_now())])
    results = runner.run_checks(PARTNER, adapters=[lazy])
    assert [(r.check, r.result, r.reason) for r in results] == [
        ("one", TRUE, None),
        ("two", "UNKNOWN", "SOURCE_UNAVAILABLE"),
    ]


def test_req_func_039_adapter_cannot_answer_checks_of_another_source():
    def run(self, partner, deadline):
        return [
            CheckResult("vatValid", FALSE, "A", utc_now()),  # belongs to VIES
            CheckResult("one", FALSE, "VIES", utc_now()),  # wrong source name
            self.result("one", TRUE, utc_now()),
        ]

    with mock.patch(
        "checks.sources.vies.query_vies", return_value=({"valid": True, "name": "Muster Bau GmbH"}, utc_now())
    ):
        results = runner.run_checks(PARTNER, adapters=[ViesAdapter(), adapter("A", ("one",), run=run)])
    assert [(r.check, r.result, r.source) for r in results] == [
        ("vatValid", TRUE, "VIES"),
        ("nameMatchesVat", TRUE, "VIES"),
        ("one", TRUE, "A"),
    ]


def test_req_func_039_results_follow_the_declared_order():
    def run(self, partner, deadline):
        return [self.result("two", FALSE, utc_now()), self.result("one", TRUE, utc_now())]

    results = runner.run_checks(PARTNER, adapters=[adapter("A", ("one", "two"), run=run)])
    assert [r.check for r in results] == ["one", "two"]


def test_req_func_039_adapter_returning_nothing_is_unknown():
    results = runner.run_checks(PARTNER, adapters=[adapter("A", ("one",), run=lambda self, p, d: None)])
    assert [(r.result, r.reason) for r in results] == [("UNKNOWN", "SOURCE_UNAVAILABLE")]


# --- No adapter code on the failure path (review of SCRUM-59) ---


class OwnUnavailableAdapter(SourceAdapter):
    """Like the HFU adapter: overrides unavailable() with another signature, then fails or overruns."""

    source = "OWN"
    checks = ("ownCheck",)

    def __init__(self, sleep=0):
        self.sleep = sleep

    def unavailable(self, stichtag, error):
        raise AssertionError("the runner must not call adapter code when the source failed")

    def run(self, partner, deadline):
        if self.sleep:
            time.sleep(self.sleep)
        raise RuntimeError("source is down")


@pytest.mark.parametrize("sleep", [0, 1], ids=["raises", "overruns the budget"])
def test_req_func_039_failure_path_runs_no_adapter_code(monkeypatch, sleep):
    monkeypatch.setattr(runner, "SOURCE_TIME_BUDGET", 0.2)
    with mock.patch(
        "checks.sources.vies.query_vies", return_value=({"valid": True, "name": "Muster Bau GmbH"}, utc_now())
    ):
        results = runner.run_checks(PARTNER, adapters=[OwnUnavailableAdapter(sleep), ViesAdapter()])
    assert [(r.check, r.result, r.reason) for r in results] == [
        ("ownCheck", "UNKNOWN", "SOURCE_UNAVAILABLE"),
        ("vatValid", TRUE, None),
        ("nameMatchesVat", TRUE, None),
    ]


def test_req_func_039_duplicate_result_keeps_the_first(caplog):
    def run(self, partner, deadline):
        return [self.result("one", TRUE, utc_now()), self.result("one", FALSE, utc_now())]

    results = runner.run_checks(PARTNER, adapters=[adapter("A", ("one",), run=run)])
    assert [(r.check, r.result) for r in results] == [("one", TRUE)]
    assert "returned one twice" in caplog.text
