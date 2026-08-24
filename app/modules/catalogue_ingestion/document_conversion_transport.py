"""Bounded filesystem transport for the isolated Docling worker.

The API/ingestion process and the Docling container deliberately share only a
small job volume.  The application writes admitted PDF bytes and fixed limits;
the worker returns a JSON result.  Neither side obtains a network connection,
database credential, URL, or application configuration through this boundary.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from app.modules.catalogue_ingestion.document_conversion import (
    DocumentConversionError,
    _document_worker_environment,
    _terminate_worker_process_tree,
)

if TYPE_CHECKING:
    from app.modules.catalogue_ingestion.document_conversion import DocumentConversionLimits


JOB_SCHEMA_VERSION = "catalogue-docling-job.v1"
_MAX_PENDING_JOBS = 128
_MAX_DOCUMENT_BYTES = 20_000_000
_MAX_RESULT_OR_CANCELLATION_AGE_SECONDS = 300
_RESULT_ERROR_CODES = frozenset(
    {
        "document_conversion_failed",
        "document_conversion_invalid_output",
        "document_conversion_timeout",
    }
)


class DocumentWorkerTransportError(DocumentConversionError):
    """Stable errors raised at the application-to-worker boundary."""


class FilesystemDoclingWorker:
    """Submit one PDF job to the restricted worker and wait only to its deadline."""

    def __init__(
        self,
        *,
        job_root: str | None,
        poll_interval_milliseconds: int = 50,
        max_pending_jobs: int = 32,
    ) -> None:
        self.job_root = Path(job_root) if job_root else None
        if not 1 <= poll_interval_milliseconds <= 1_000:
            raise ValueError("poll interval must be between 1 and 1,000 milliseconds")
        if not 1 <= max_pending_jobs <= _MAX_PENDING_JOBS:
            raise ValueError(f"max pending jobs must be between 1 and {_MAX_PENDING_JOBS}")
        self.poll_interval_seconds = poll_interval_milliseconds / 1_000
        self.max_pending_jobs = max_pending_jobs

    def convert(self, payload: bytes, *, enable_ocr: bool, limits: DocumentConversionLimits) -> str:
        if self.job_root is None:
            raise DocumentWorkerTransportError("document_worker_transport_unavailable")
        if len(payload) > limits.max_bytes:
            raise DocumentWorkerTransportError("document_byte_limit_exceeded")

        layout = _job_layout(self.job_root)
        try:
            for directory in layout.values():
                directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DocumentWorkerTransportError("document_worker_transport_unavailable") from exc
        if _outstanding_job_count(layout) >= self.max_pending_jobs:
            raise DocumentWorkerTransportError("document_worker_queue_full")

        job_id = uuid.uuid4().hex
        deadline = time.monotonic() + limits.max_runtime_seconds
        temporary = layout["requests"] / f".{job_id}.tmp"
        request = layout["requests"] / job_id
        try:
            temporary.mkdir()
            (temporary / "input.pdf").write_bytes(payload)
            (temporary / "request.json").write_text(
                json.dumps(
                    _request_payload(
                        enable_ocr=enable_ocr,
                        limits=limits,
                        deadline_unix_seconds=time.time() + limits.max_runtime_seconds,
                    ),
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            temporary.replace(request)
        except OSError as exc:
            shutil.rmtree(temporary, ignore_errors=True)
            raise DocumentWorkerTransportError("document_worker_transport_unavailable") from exc

        result_path = layout["results"] / f"{job_id}.json"
        try:
            while time.monotonic() < deadline:
                if result_path.is_file():
                    return _read_result(
                        result_path, max_output_characters=limits.max_output_characters
                    )
                time.sleep(self.poll_interval_seconds)
        finally:
            if result_path.is_file():
                result_path.unlink(missing_ok=True)

        # A queued worker checks this marker before and after conversion.  A
        # late result is never consumed after the caller's deadline elapsed.
        # The caller's deadline is authoritative even if a disappearing volume
        # prevents best-effort cancellation notification.
        with suppress(OSError):
            (layout["cancellations"] / job_id).touch(exist_ok=True)
        raise DocumentWorkerTransportError("document_conversion_timeout")


class FilesystemDoclingJobServer:
    """Dedicated-worker side of the job volume protocol.

    Each conversion is a fresh child process so a per-job timeout cannot leave
    Docling loaded in the long-running volume supervisor.  The container's
    cgroup remains the hard CPU/memory/PID boundary.
    """

    def __init__(self, *, job_root: str, poll_interval_milliseconds: int = 100) -> None:
        self.job_root = Path(job_root)
        self.poll_interval_seconds = poll_interval_milliseconds / 1_000

    def serve_forever(self) -> None:
        while True:
            if not self.process_next():
                time.sleep(self.poll_interval_seconds)

    def process_next(self) -> bool:
        layout = _job_layout(self.job_root)
        for directory in layout.values():
            directory.mkdir(parents=True, exist_ok=True)
        _prune_expired_messages(layout)
        _touch_heartbeat(layout)
        request = next(
            (
                path
                for path in sorted(layout["requests"].iterdir())
                if path.is_dir() and not path.name.startswith(".")
            ),
            None,
        )
        if request is None:
            return False
        processing = layout["processing"] / request.name
        try:
            request.replace(processing)
        except OSError:
            return True
        try:
            if (layout["cancellations"] / processing.name).exists():
                return True
            result = self._run(processing)
            if not (layout["cancellations"] / processing.name).exists():
                _write_json_atomically(layout["results"] / f"{processing.name}.json", result)
        finally:
            shutil.rmtree(processing, ignore_errors=True)
            (layout["cancellations"] / processing.name).unlink(missing_ok=True)
            _touch_heartbeat(layout)
        return True

    def _run(self, job_path: Path) -> dict[str, str]:
        try:
            request = _read_request(job_path / "request.json")
            remaining_seconds = request["deadline_unix_seconds"] - time.time()
            if remaining_seconds <= 0:
                return {"status": "error", "code": "document_conversion_timeout"}
            command = [
                sys.executable,
                "-m",
                "app.modules.catalogue_ingestion.document_conversion_worker",
                "--input",
                str(job_path / "input.pdf"),
                "--output",
                str(job_path / "output.json"),
                "--max-pages",
                str(request["max_pages"]),
                "--max-file-bytes",
                str(request["max_bytes"]),
                "--max-output-characters",
                str(request["max_output_characters"]),
            ]
            if request["enable_ocr"]:
                command.append("--enable-ocr")
            popen_kwargs: dict[str, object] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "env": _document_worker_environment(),
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                ) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(command, **popen_kwargs)
            try:
                process.communicate(
                    timeout=min(float(request["max_runtime_seconds"]), remaining_seconds)
                )
            except subprocess.TimeoutExpired:
                _terminate_worker_process_tree(process)
                return {"status": "error", "code": "document_conversion_timeout"}
            if process.returncode != 0:
                return {"status": "error", "code": "document_conversion_failed"}
            parsed = json.loads((job_path / "output.json").read_text(encoding="utf-8"))
            text = parsed["text"]
            if not isinstance(text, str) or len(text) > request["max_output_characters"]:
                return {"status": "error", "code": "document_conversion_invalid_output"}
            return {"status": "ok", "text": text}
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            return {"status": "error", "code": "document_conversion_failed"}


def _job_layout(root: Path) -> dict[str, Path]:
    return {
        "requests": root / "requests",
        "processing": root / "processing",
        "results": root / "results",
        "cancellations": root / "cancellations",
        "health": root / "health",
    }


def _outstanding_job_count(layout: dict[str, Path]) -> int:
    return sum(
        1
        for directory in (layout["requests"], layout["processing"])
        for path in directory.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def _request_payload(
    *,
    enable_ocr: bool,
    limits: DocumentConversionLimits,
    deadline_unix_seconds: float,
) -> dict[str, object]:
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "enable_ocr": enable_ocr,
        "max_bytes": limits.max_bytes,
        "max_pages": limits.max_pages,
        "max_runtime_seconds": limits.max_runtime_seconds,
        "max_output_characters": limits.max_output_characters,
        "deadline_unix_seconds": deadline_unix_seconds,
    }


def _read_request(path: Path) -> dict[str, int | bool | float]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or parsed.get("schema_version") != JOB_SCHEMA_VERSION:
        raise ValueError("invalid_job_request")
    values = {
        name: parsed.get(name)
        for name in ("max_bytes", "max_pages", "max_runtime_seconds", "max_output_characters")
    }
    deadline = parsed.get("deadline_unix_seconds")
    if (
        not isinstance(parsed.get("enable_ocr"), bool)
        or any(not isinstance(value, int) or value < 1 for value in values.values())
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
        or values["max_pages"] > 500
        or values["max_bytes"] > _MAX_DOCUMENT_BYTES
        or values["max_runtime_seconds"] > 300
        or values["max_output_characters"] > 2_000_000
    ):
        raise ValueError("invalid_job_request")
    return {"enable_ocr": parsed["enable_ocr"], **values, "deadline_unix_seconds": float(deadline)}  # type: ignore[dict-item]


def _read_result(path: Path, *, max_output_characters: int) -> str:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise DocumentWorkerTransportError("document_conversion_invalid_output") from exc
    if not isinstance(parsed, dict):
        raise DocumentWorkerTransportError("document_conversion_invalid_output")
    if parsed.get("status") == "ok" and isinstance(parsed.get("text"), str):
        text = parsed["text"]
        if len(text) <= max_output_characters:
            return text
    if parsed.get("status") == "error" and parsed.get("code") in _RESULT_ERROR_CODES:
        raise DocumentWorkerTransportError(parsed["code"])
    raise DocumentWorkerTransportError("document_conversion_invalid_output")


def _write_json_atomically(path: Path, payload: dict[str, str]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _touch_heartbeat(layout: dict[str, Path]) -> None:
    (layout["health"] / "worker-heartbeat").touch(exist_ok=True)


def _prune_expired_messages(layout: dict[str, Path]) -> None:
    cutoff = time.time() - _MAX_RESULT_OR_CANCELLATION_AGE_SECONDS
    for directory_name in ("results", "cancellations"):
        try:
            candidates = tuple(layout[directory_name].iterdir())
        except OSError:
            continue
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                    candidate.unlink()
            except OSError:
                continue
