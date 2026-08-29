"""Quarantined, layout-aware catalogue document conversion.

This module deliberately has no networking capability.  Bytes must first pass
``SafeSourceFetcher``; only then can a bounded PDF be handed to a short-lived
Docling child process.  OCR is a second, explicitly measured attempt and is
never used merely because a document happens to be a PDF.
"""

from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.modules.opportunities.source_monitor import NormalizedSourcePayload, SourceFetchError

DOCUMENT_CONVERTER_VERSION = "catalogue-docling-layout.v1"
LOCAL_PDF_PARSER_VERSION = "catalogue-pypdf-text.v1"
DEFAULT_DOCUMENT_MODEL_ARTIFACTS_PATH = "/opt/docling/models"


class DocumentConversionError(SourceFetchError):
    """Stable, safe-to-record conversion failure code."""


@dataclass(frozen=True, slots=True)
class DocumentConversionLimits:
    max_bytes: int
    max_pages: int
    max_runtime_seconds: int
    max_output_characters: int
    min_text_characters: int

    def __post_init__(self) -> None:
        if (
            min(
                self.max_bytes,
                self.max_pages,
                self.max_runtime_seconds,
                self.max_output_characters,
                self.min_text_characters,
            )
            < 1
        ):
            raise ValueError("document conversion limits must be positive")


@dataclass(frozen=True, slots=True)
class ConvertedDocument:
    text: str
    page_count: int
    used_ocr: bool
    converter_version: str = DOCUMENT_CONVERTER_VERSION


class LayoutConversionWorker(Protocol):
    """The process boundary used by the in-process policy controller."""

    def convert(
        self, payload: bytes, *, enable_ocr: bool, limits: DocumentConversionLimits
    ) -> str: ...


class SubprocessDoclingWorker:
    """Run Docling without application configuration, sockets, or DB access.

    Production deployment still must place this executable in the dedicated
    document-worker sandbox with restricted egress and resource limits.  This
    boundary enforces the application-side timeout and avoids loading untrusted
    documents into the API/queue worker process.
    """

    def __init__(
        self, *, model_artifacts_path: str = DEFAULT_DOCUMENT_MODEL_ARTIFACTS_PATH
    ) -> None:
        self.model_artifacts_path = model_artifacts_path

    def convert(self, payload: bytes, *, enable_ocr: bool, limits: DocumentConversionLimits) -> str:
        with tempfile.TemporaryDirectory(prefix="scholarship-document-quarantine-") as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.pdf"
            output_path = root / "output.json"
            input_path.write_bytes(payload)
            command = [
                sys.executable,
                "-m",
                "app.modules.catalogue_ingestion.document_conversion_worker",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--max-pages",
                str(limits.max_pages),
                "--max-file-bytes",
                str(limits.max_bytes),
                "--max-output-characters",
                str(limits.max_output_characters),
            ]
            if enable_ocr:
                command.append("--enable-ocr")
            popen_kwargs: dict[str, object] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                # Do not inherit application secrets/configuration.  The
                # worker needs only enough environment for the interpreter
                # and native libraries to start.
                "env": _document_worker_environment(model_artifacts_path=self.model_artifacts_path),
            }
            if os.name == "nt":
                # A dedicated process group lets taskkill terminate Docling's
                # own helper processes on deadline expiry.
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                ) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                # The isolated session gives the supervisor one process group
                # to terminate rather than leaving child helpers behind.
                popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(command, **popen_kwargs)
            try:
                process.communicate(timeout=limits.max_runtime_seconds)
            except subprocess.TimeoutExpired as exc:
                _terminate_worker_process_tree(process)
                raise DocumentConversionError("document_conversion_timeout") from exc
            if process.returncode != 0 or not output_path.is_file():
                raise DocumentConversionError("document_conversion_failed")
            try:
                parsed = json.loads(output_path.read_text(encoding="utf-8"))
                text = parsed["text"]
            except (OSError, TypeError, ValueError, KeyError) as exc:
                raise DocumentConversionError("document_conversion_invalid_output") from exc
            if not isinstance(text, str):
                raise DocumentConversionError("document_conversion_invalid_output")
            return text


def _terminate_worker_process_tree(process: subprocess.Popen[str]) -> None:
    """Stop a timed-out converter and every helper it created.

    Docling can start native/model helper processes.  Killing only the Python
    entry process lets those helpers continue consuming CPU after the catalogue
    run has failed.  This is a local deadline backstop; the production worker
    must still enforce cgroup/container limits and restricted egress.
    """

    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                _kill_worker_process(process)
        except (OSError, subprocess.TimeoutExpired):
            # A direct kill is still better than leaving the main converter
            # alive when taskkill is unavailable or constrained by policy.
            _kill_worker_process(process)
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            _kill_worker_process(process)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _kill_worker_process(process)
        process.wait(timeout=5)


def _kill_worker_process(process: subprocess.Popen[str]) -> None:
    """Use Popen's direct-kill backstop when one is available.

    Real ``subprocess.Popen`` instances always implement ``kill``.  Keeping the
    fallback defensive also lets timeout handling retain its primary
    process-group cleanup behavior when a narrow process-like test double is
    used by an embedding application.
    """

    kill = getattr(process, "kill", None)
    if callable(kill):
        kill()


class LayoutAwareDocumentConverter:
    """Validate PDF limits and enforce the deterministic-text then OCR ladder."""

    def __init__(
        self,
        *,
        limits: DocumentConversionLimits,
        worker: LayoutConversionWorker | None = None,
        model_artifacts_path: str = DEFAULT_DOCUMENT_MODEL_ARTIFACTS_PATH,
    ) -> None:
        self.limits = limits
        self.worker = worker or SubprocessDoclingWorker(model_artifacts_path=model_artifacts_path)

    def normalize(self, payload: bytes, content_type: str, *, allow_ocr: bool = False) -> str:
        if content_type != "application/pdf":
            raise DocumentConversionError("document_content_type_not_supported")
        return self.convert_pdf(payload, allow_ocr=allow_ocr).text

    def convert_pdf(self, payload: bytes, *, allow_ocr: bool = False) -> ConvertedDocument:
        self._validate_pdf(payload)
        page_count = self._page_count(payload)
        text = self._convert(payload, enable_ocr=False)
        if self._is_text_sufficient(text):
            return ConvertedDocument(text=text, page_count=page_count, used_ocr=False)
        if not allow_ocr:
            raise DocumentConversionError("document_text_insufficient")
        ocr_text = self._convert(payload, enable_ocr=True)
        if not self._is_text_sufficient(ocr_text):
            raise DocumentConversionError("document_ocr_text_insufficient")
        return ConvertedDocument(text=ocr_text, page_count=page_count, used_ocr=True)

    def _validate_pdf(self, payload: bytes) -> None:
        if len(payload) > self.limits.max_bytes:
            raise DocumentConversionError("document_byte_limit_exceeded")
        if not payload.startswith(b"%PDF-"):
            raise DocumentConversionError("document_content_sniff_mismatch")

    def _page_count(self, payload: bytes) -> int:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(payload), strict=True)
            if reader.is_encrypted:
                raise DocumentConversionError("document_encrypted")
            page_count = len(reader.pages)
        except DocumentConversionError:
            raise
        except Exception as exc:
            raise DocumentConversionError("document_malformed_pdf") from exc
        if page_count > self.limits.max_pages:
            raise DocumentConversionError("document_page_limit_exceeded")
        return page_count

    def _convert(self, payload: bytes, *, enable_ocr: bool) -> str:
        try:
            text = self.worker.convert(payload, enable_ocr=enable_ocr, limits=self.limits)
        except DocumentConversionError:
            raise
        except Exception as exc:
            raise DocumentConversionError("document_conversion_failed") from exc
        if len(text) > self.limits.max_output_characters:
            raise DocumentConversionError("document_output_limit_exceeded")
        return text

    def _is_text_sufficient(self, text: str) -> bool:
        compact = "".join(text.split())
        if len(compact) < self.limits.min_text_characters:
            return False
        meaningful = sum(character.isalnum() for character in compact)
        return meaningful * 2 >= len(compact)


class CatalogueDocumentPayloadNormalizer:
    """Apply Docling only to PDFs after SafeSourceFetcher has admitted them."""

    parser_version = DOCUMENT_CONVERTER_VERSION

    def __init__(self, *, converter: LayoutAwareDocumentConverter, allow_ocr: bool) -> None:
        self.converter = converter
        self.allow_ocr = allow_ocr

    def __call__(self, payload: bytes, content_type: str) -> str | NormalizedSourcePayload:
        if content_type == "application/pdf":
            # Ordinary text PDFs stay in-process.  Only a document whose local
            # text layer is insufficient crosses the isolated Docling boundary.
            self.converter._validate_pdf(payload)
            page_count = self.converter._page_count(payload)
            from app.modules.opportunities.source_monitor import normalize_source_payload

            local_text = normalize_source_payload(payload, content_type)
            if self.converter._is_text_sufficient(local_text):
                return NormalizedSourcePayload(
                    text=local_text,
                    parser_version=LOCAL_PDF_PARSER_VERSION,
                    conversion_metadata={
                        "document_page_count": page_count,
                        "document_ocr_decision": "not_used",
                        "document_ocr_reason": "local_text_sufficient",
                    },
                )
            converted = self.converter.convert_pdf(payload, allow_ocr=self.allow_ocr)
            return NormalizedSourcePayload(
                text=converted.text,
                parser_version=converted.converter_version,
                conversion_metadata={
                    "document_page_count": converted.page_count,
                    "document_ocr_decision": "used" if converted.used_ocr else "not_used",
                    "document_ocr_reason": (
                        "text_insufficient_ocr_succeeded"
                        if converted.used_ocr
                        else "text_sufficient"
                    ),
                },
            )
        # Non-document content remains under the existing deterministic HTML/
        # text normalizer; Docling is never a general web-content parser.
        from app.modules.opportunities.source_monitor import normalize_source_payload

        return normalize_source_payload(payload, content_type)


def _document_worker_environment(
    *, model_artifacts_path: str = DEFAULT_DOCUMENT_MODEL_ARTIFACTS_PATH
) -> dict[str, str]:
    """Return the minimal interpreter environment without application secrets."""

    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "PYTHONHOME", "TEMP", "TMP")
    environment = {name: os.environ[name] for name in allowed if os.environ.get(name)}
    # Production images must bake reviewed Docling models. A converter worker
    # never downloads a model at runtime, which would violate restricted egress
    # and make parser output non-reproducible.
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    # Docling resolves its cache root during import. Pin it to the reviewed
    # artifact mount instead of inheriting the API/worker account's home
    # directory, which could contain mutable unreviewed model state.
    environment["HOME"] = model_artifacts_path
    environment["USERPROFILE"] = model_artifacts_path
    environment["DOCLING_ARTIFACTS_PATH"] = model_artifacts_path
    return environment


__all__ = [
    "DEFAULT_DOCUMENT_MODEL_ARTIFACTS_PATH",
    "DOCUMENT_CONVERTER_VERSION",
    "LOCAL_PDF_PARSER_VERSION",
    "CatalogueDocumentPayloadNormalizer",
    "ConvertedDocument",
    "DocumentConversionError",
    "DocumentConversionLimits",
    "LayoutAwareDocumentConverter",
    "LayoutConversionWorker",
    "SubprocessDoclingWorker",
]
