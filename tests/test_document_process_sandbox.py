import os
import time

import pytest

from app.modules.document_lab.process_sandbox import (
    BoundedProcessFailed,
    BoundedProcessTimeout,
    run_bounded_process,
)


def _return_value(value: str) -> str:
    return value


def _sleep_then_return(delay: float) -> str:
    time.sleep(delay)
    return "late"


def _raise_private_failure() -> None:
    raise RuntimeError("private document content must not cross process boundary")


def _child_pid() -> int:
    return os.getpid()


def test_bounded_process_returns_picklable_result() -> None:
    assert run_bounded_process(_return_value, ("ok",), timeout_seconds=2) == "ok"


def test_bounded_process_runs_outside_parent_process() -> None:
    assert run_bounded_process(_child_pid, (), timeout_seconds=2) != os.getpid()


def test_bounded_process_hard_stops_after_deadline() -> None:
    started = time.monotonic()
    with pytest.raises(BoundedProcessTimeout):
        run_bounded_process(_sleep_then_return, (2.0,), timeout_seconds=0.1)
    assert time.monotonic() - started < 1.5


def test_bounded_process_returns_only_safe_failure_category() -> None:
    with pytest.raises(BoundedProcessFailed) as exc_info:
        run_bounded_process(_raise_private_failure, (), timeout_seconds=2)
    assert str(exc_info.value) == "RuntimeError"
    assert "private document" not in str(exc_info.value)
