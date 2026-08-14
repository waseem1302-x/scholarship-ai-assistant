"""Bounded subprocess execution for untrusted document parsing.

This module deliberately keeps the parsing boundary independent from HTTP and
from the document worker. A parser receives only immutable bytes/configuration
and returns a picklable value. The parent owns the wall-clock deadline and will
terminate, then kill, a parser process that does not exit in time.

On POSIX platforms the child also applies conservative resource limits before
calling the parser. Production still keeps Document Lab gated until deployment
isolation (including no-network/restricted-filesystem controls) is evidenced.
"""

from __future__ import annotations

import math
import multiprocessing as mp
import os
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any, TypeVar

T = TypeVar("T")


class BoundedProcessTimeout(RuntimeError):
    """The child exceeded its wall-clock deadline and was forcibly stopped."""


class BoundedProcessFailed(RuntimeError):
    """The child exited/crashed without returning a usable result."""


@dataclass(frozen=True)
class ProcessLimits:
    """Conservative parser limits; intentionally independent of user input."""

    memory_bytes: int = 512 * 1024 * 1024
    open_files: int = 64
    output_file_bytes: int = 8 * 1024 * 1024


def run_bounded_process(
    function: Callable[..., T],
    args: tuple[Any, ...],
    *,
    timeout_seconds: int,
    limits: ProcessLimits | None = None,
) -> T:
    """Run ``function`` in a fresh process with a hard parent-owned deadline.

    ``ProcessPoolExecutor`` cancellation cannot guarantee that a running parser
    has actually stopped. This function owns the concrete child process so it
    can terminate and, if necessary, kill it before returning a timeout.
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    ctx = mp.get_context("spawn")
    parent_connection, child_connection = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_child_entry,
        args=(
            child_connection,
            function,
            args,
            timeout_seconds,
            limits or ProcessLimits(),
        ),
        daemon=True,
    )
    process.start()
    child_connection.close()

    try:
        process.join(timeout_seconds)
        if process.is_alive():
            _stop_process(process)
            raise BoundedProcessTimeout("Parser process exceeded its deadline")

        if not parent_connection.poll(0.25):
            raise BoundedProcessFailed(
                f"Parser process exited without a result (exitcode={process.exitcode})"
            )

        status, payload = parent_connection.recv()
        if status == "ok":
            return payload
        raise BoundedProcessFailed(str(payload))
    finally:
        parent_connection.close()
        if process.is_alive():
            _stop_process(process)
        process.close()


def _stop_process(process: mp.Process) -> None:
    """Guarantee the parser is gone before the caller continues."""

    process.terminate()
    process.join(1)
    if process.is_alive():
        process.kill()
        process.join(1)
    if process.is_alive():
        raise BoundedProcessFailed("Parser process could not be terminated")


def _child_entry(
    connection: Connection,
    function: Callable[..., T],
    args: tuple[Any, ...],
    timeout_seconds: int,
    limits: ProcessLimits,
) -> None:
    try:
        _apply_posix_limits(timeout_seconds, limits)
        result = function(*args)
        connection.send(("ok", result))
    except BaseException as exc:  # child boundary converts failures to safe categories
        try:
            connection.send(("error", type(exc).__name__))
        except BaseException:
            pass
    finally:
        connection.close()


def _apply_posix_limits(timeout_seconds: int, limits: ProcessLimits) -> None:
    """Apply hard CPU/memory/fd/output limits where the OS supports them."""

    if os.name != "posix":
        return

    import resource

    cpu_seconds = max(1, math.ceil(timeout_seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits.open_files, limits.open_files))
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (limits.output_file_bytes, limits.output_file_bytes),
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
