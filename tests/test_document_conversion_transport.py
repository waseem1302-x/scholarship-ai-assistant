"""Focused contract tests for the application-to-Docling job volume."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.catalogue_ingestion import document_conversion_transport
from app.modules.catalogue_ingestion.document_conversion import DocumentConversionLimits
from app.modules.catalogue_ingestion.document_conversion_transport import (
    DocumentWorkerTransportError,
    FilesystemDoclingJobServer,
    FilesystemDoclingWorker,
)


def _limits(**overrides: int) -> DocumentConversionLimits:
    return DocumentConversionLimits(
        max_bytes=overrides.get("max_bytes", 1_000),
        max_pages=overrides.get("max_pages", 5),
        max_runtime_seconds=overrides.get("max_runtime_seconds", 2),
        max_output_characters=overrides.get("max_output_characters", 1_000),
        min_text_characters=1,
    )


def _wait_for_request(root: Path) -> Path:
    deadline = time.monotonic() + 1
    requests = root / "requests"
    while time.monotonic() < deadline:
        if not requests.is_dir():
            time.sleep(0.01)
            continue
        found = [
            path for path in requests.iterdir() if path.is_dir() and not path.name.startswith(".")
        ]
        if found:
            return found[0]
        time.sleep(0.01)
    raise AssertionError("transport did not publish a job")


def _publish_result_atomically(path: Path, payload: dict[str, str]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def test_filesystem_transport_publishes_only_bounded_job_data_and_reads_atomic_result(
    tmp_path: Path,
) -> None:
    worker = FilesystemDoclingWorker(
        job_root=str(tmp_path), poll_interval_milliseconds=1, max_pending_jobs=2
    )
    response: list[str] = []

    thread = threading.Thread(
        target=lambda: response.append(
            worker.convert(b"%PDF-job", enable_ocr=False, limits=_limits())
        )
    )
    thread.start()
    request = _wait_for_request(tmp_path)

    assert (request / "input.pdf").read_bytes() == b"%PDF-job"
    submitted = json.loads((request / "request.json").read_text(encoding="utf-8"))
    assert submitted == {
        "schema_version": "catalogue-docling-job.v1",
        "enable_ocr": False,
        "max_bytes": 1_000,
        "max_pages": 5,
        "max_runtime_seconds": 2,
        "max_output_characters": 1_000,
        "deadline_unix_seconds": submitted["deadline_unix_seconds"],
    }
    assert submitted["deadline_unix_seconds"] >= time.time()
    (tmp_path / "results").mkdir(exist_ok=True)
    _publish_result_atomically(
        tmp_path / "results" / f"{request.name}.json",
        {"status": "ok", "text": "# Converted\n\n| A | B |"},
    )
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert response == ["# Converted\n\n| A | B |"]
    assert not (tmp_path / "results" / f"{request.name}.json").exists()


def test_filesystem_transport_returns_only_safe_worker_errors(tmp_path: Path) -> None:
    worker = FilesystemDoclingWorker(job_root=str(tmp_path), poll_interval_milliseconds=1)
    errors: list[BaseException] = []

    def submit() -> None:
        try:
            worker.convert(b"%PDF-job", enable_ocr=True, limits=_limits())
        except BaseException as exc:  # pragma: no cover - assertion follows thread handoff
            errors.append(exc)

    thread = threading.Thread(target=submit)
    thread.start()
    request = _wait_for_request(tmp_path)
    _publish_result_atomically(
        tmp_path / "results" / f"{request.name}.json",
        {"status": "error", "code": "document_conversion_failed"},
    )
    thread.join(timeout=1)

    assert len(errors) == 1
    assert isinstance(errors[0], DocumentWorkerTransportError)
    assert str(errors[0]) == "document_conversion_failed"


def test_filesystem_transport_cancels_an_unanswered_job_at_its_deadline(
    tmp_path: Path, monkeypatch
) -> None:
    worker = FilesystemDoclingWorker(job_root=str(tmp_path), poll_interval_milliseconds=1)
    clock = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(
        document_conversion_transport,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None, time=time.time),
    )

    with pytest.raises(DocumentWorkerTransportError, match="document_conversion_timeout"):
        worker.convert(b"%PDF-job", enable_ocr=False, limits=_limits(max_runtime_seconds=1))

    cancellations = list((tmp_path / "cancellations").iterdir())
    assert len(cancellations) == 1
    assert cancellations[0].name.isalnum()


def test_filesystem_transport_applies_a_bounded_pending_queue(tmp_path: Path) -> None:
    requests = tmp_path / "requests"
    requests.mkdir(parents=True)
    (requests / "already-queued").mkdir()
    worker = FilesystemDoclingWorker(job_root=str(tmp_path), max_pending_jobs=1)

    with pytest.raises(DocumentWorkerTransportError, match="document_worker_queue_full"):
        worker.convert(b"%PDF-job", enable_ocr=False, limits=_limits())


def test_filesystem_transport_counts_an_in_flight_job_against_the_queue_bound(
    tmp_path: Path,
) -> None:
    processing = tmp_path / "processing" / "already-running"
    processing.mkdir(parents=True)
    worker = FilesystemDoclingWorker(job_root=str(tmp_path), max_pending_jobs=1)

    with pytest.raises(DocumentWorkerTransportError, match="document_worker_queue_full"):
        worker.convert(b"%PDF-job", enable_ocr=False, limits=_limits())


def test_dedicated_server_claims_job_emits_result_and_cleans_input(
    tmp_path: Path, monkeypatch
) -> None:
    request = tmp_path / "requests" / "job-123"
    request.mkdir(parents=True)
    (request / "input.pdf").write_bytes(b"%PDF-job")
    (request / "request.json").write_text("{}", encoding="utf-8")
    server = FilesystemDoclingJobServer(job_root=str(tmp_path), poll_interval_milliseconds=1)
    monkeypatch.setattr(server, "_run", lambda _: {"status": "ok", "text": "Converted"})

    assert server.process_next() is True
    assert json.loads((tmp_path / "results" / "job-123.json").read_text(encoding="utf-8")) == {
        "status": "ok",
        "text": "Converted",
    }
    assert not request.exists()
    assert (tmp_path / "health" / "worker-heartbeat").is_file()


def test_dedicated_server_rejects_an_expired_job_without_starting_docling(
    tmp_path: Path, monkeypatch
) -> None:
    request = tmp_path / "requests" / "expired-job"
    request.mkdir(parents=True)
    (request / "input.pdf").write_bytes(b"%PDF-job")
    (request / "request.json").write_text(
        json.dumps(
            {
                "schema_version": "catalogue-docling-job.v1",
                "enable_ocr": False,
                "max_bytes": 1_000,
                "max_pages": 5,
                "max_runtime_seconds": 2,
                "max_output_characters": 1_000,
                "deadline_unix_seconds": time.time() - 1,
            }
        ),
        encoding="utf-8",
    )
    server = FilesystemDoclingJobServer(job_root=str(tmp_path))
    monkeypatch.setattr(
        document_conversion_transport.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("expired job must not start Docling"),
    )

    assert server.process_next() is True
    assert json.loads((tmp_path / "results" / "expired-job.json").read_text(encoding="utf-8")) == {
        "status": "error",
        "code": "document_conversion_timeout",
    }


def test_dedicated_server_prunes_abandoned_transport_messages(tmp_path: Path) -> None:
    results = tmp_path / "results"
    cancellations = tmp_path / "cancellations"
    results.mkdir(parents=True)
    cancellations.mkdir()
    stale_result = results / "orphaned.json"
    stale_cancellation = cancellations / "orphaned"
    stale_result.write_text("{}", encoding="utf-8")
    stale_cancellation.touch()
    old_timestamp = time.time() - 301
    for path in (stale_result, stale_cancellation):
        path.touch()
        path.stat()
        os.utime(path, (old_timestamp, old_timestamp))

    assert FilesystemDoclingJobServer(job_root=str(tmp_path)).process_next() is False
    assert not stale_result.exists()
    assert not stale_cancellation.exists()


def test_dedicated_server_timeout_terminates_its_docling_process_tree(
    tmp_path: Path, monkeypatch
) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "catalogue-docling-job.v1",
                "enable_ocr": False,
                "max_bytes": 1_000,
                "max_pages": 5,
                "max_runtime_seconds": 2,
                "max_output_characters": 1_000,
                "deadline_unix_seconds": time.time() + 2,
            }
        ),
        encoding="utf-8",
    )

    class TimedOutProcess:
        def communicate(self, **_kwargs) -> None:
            raise subprocess.TimeoutExpired("docling", 1)

    process = TimedOutProcess()
    terminated: list[object] = []
    monkeypatch.setattr(
        document_conversion_transport.subprocess, "Popen", lambda *_a, **_k: process
    )
    monkeypatch.setattr(
        document_conversion_transport,
        "_terminate_worker_process_tree",
        terminated.append,
    )

    result = FilesystemDoclingJobServer(job_root=str(tmp_path))._run(tmp_path)

    assert result == {"status": "error", "code": "document_conversion_timeout"}
    assert terminated == [process]
