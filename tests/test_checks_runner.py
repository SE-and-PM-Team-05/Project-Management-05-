"""SCRUM-60: checks run in parallel, each source has 8 s including one retry (REQ-FUNC-039, REQ-REL-001,
REQ-REL-003, REQ-INT-013). No test calls a real source."""

import time
from unittest import mock

import pytest
import requests

from checks import runner
from checks.results import TRUE, Partner, utc_now
from checks.sources.base import SourceAdapter
from checks.sources.http import SourceUnavailable, post_within_budget

PARTNER = Partner(vat_number="ATU12345678", company_name="Muster Bau GmbH")
URL = "https://source.example/check"


class SleepingAdapter(SourceAdapter):
    """Answers TRUE after `seconds`."""

    def __init__(self, source, seconds):
        self.source = source
        self.checks = (f"{source.lower()}Check",)
        self.seconds = seconds

    def run(self, partner, deadline):
        time.sleep(self.seconds)
        return [self.result(self.checks[0], TRUE, utc_now())]


class FailingAdapter(SourceAdapter):
    source = "FAILING"
    checks = ("failingCheck",)

    def run(self, partner, deadline):
        raise ConnectionError("source is down")


def response(status):
    return mock.Mock(status_code=status)


# --- Parallel and independent (REQ-FUNC-039) ---


def test_req_func_039_sources_run_in_parallel():
    adapters = [SleepingAdapter(name, 0.3) for name in ("A", "B", "C")]
    started = time.monotonic()
    results = runner.run_checks(PARTNER, adapters=adapters)
    # One after the other would take 0.9 s.
    assert time.monotonic() - started < 0.7
    assert [r.result for r in results] == [TRUE, TRUE, TRUE]


def test_req_func_039_slow_source_does_not_block_the_others(monkeypatch):
    monkeypatch.setattr(runner, "SOURCE_TIME_BUDGET", 0.3)
    started = time.monotonic()
    results = runner.run_checks(PARTNER, adapters=[SleepingAdapter("SLOW", 5), SleepingAdapter("FAST", 0)])
    assert time.monotonic() - started < 1
    by_source = {r.source: r for r in results}
    assert (by_source["SLOW"].result, by_source["SLOW"].reason) == ("UNKNOWN", "SOURCE_UNAVAILABLE")
    assert by_source["FAST"].result == TRUE


def test_req_rel_001_failing_source_is_unknown_and_the_others_still_answer():
    results = runner.run_checks(PARTNER, adapters=[FailingAdapter(), SleepingAdapter("OK", 0)])
    assert [(r.check, r.result, r.reason) for r in results] == [
        ("failingCheck", "UNKNOWN", "SOURCE_UNAVAILABLE"),
        ("okCheck", TRUE, None),
    ]


def test_req_int_013_default_budget_is_8_seconds():
    assert runner.SOURCE_TIME_BUDGET == 8.0


# --- One retry within the budget (REQ-REL-003, REQ-INT-013) ---


@pytest.mark.parametrize("failure", [requests.Timeout(), requests.ConnectionError(), response(503)])
def test_req_rel_003_transient_error_is_retried_once(failure):
    with mock.patch("checks.sources.http.requests.post", side_effect=[failure, response(200)]) as post:
        answer, queried_at = post_within_budget(URL, time.monotonic() + 8, json={})
    assert answer.status_code == 200
    assert post.call_count == 2
    assert queried_at <= utc_now()


def test_req_rel_003_second_failure_gives_up_with_the_last_error():
    side_effect = [requests.Timeout(), response(502)]
    with mock.patch("checks.sources.http.requests.post", side_effect=side_effect) as post:
        with pytest.raises(SourceUnavailable) as error:
            post_within_budget(URL, time.monotonic() + 8)
    assert post.call_count == 2
    assert error.value.code == "HTTP_502"


def test_req_rel_003_client_error_is_not_retried():
    with mock.patch("checks.sources.http.requests.post", return_value=response(400)) as post:
        answer, _ = post_within_budget(URL, time.monotonic() + 8)
    assert answer.status_code == 400
    assert post.call_count == 1


def test_req_int_013_retry_gets_only_the_time_that_is_left():
    def slow_timeout(url, timeout, **kwargs):
        time.sleep(0.2)
        raise requests.Timeout()

    with mock.patch("checks.sources.http.requests.post", side_effect=slow_timeout) as post:
        with pytest.raises(SourceUnavailable):
            post_within_budget(URL, time.monotonic() + 8)
    first, second = (call.kwargs["timeout"] for call in post.call_args_list)
    assert first <= 8
    assert second <= first - 0.2


def test_req_int_013_no_attempt_after_the_deadline():
    with mock.patch("checks.sources.http.requests.post") as post:
        with pytest.raises(SourceUnavailable) as error:
            post_within_budget(URL, time.monotonic() - 1)
    assert post.call_count == 0
    assert error.value.code == "TIMEOUT"


def test_req_int_013_no_retry_when_the_budget_ran_out_during_the_first_attempt():
    def answer_late(url, timeout, **kwargs):
        time.sleep(0.15)
        raise requests.Timeout()

    with mock.patch("checks.sources.http.requests.post", side_effect=answer_late) as post:
        with pytest.raises(SourceUnavailable):
            post_within_budget(URL, time.monotonic() + 0.1)
    assert post.call_count == 1
