"""Regression coverage for controlled, layout-aware catalogue PDF conversion."""

from __future__ import annotations

import io
import subprocess

import pytest
from pypdf import PdfWriter

from app.modules.catalogue_ingestion import document_conversion
from app.modules.catalogue_ingestion.document_conversion import (
    DOCUMENT_CONVERTER_VERSION,
    CatalogueDocumentPayloadNormalizer,
    DocumentConversionError,
    DocumentConversionLimits,
    LayoutAwareDocumentConverter,
    SubprocessDoclingWorker,
    _document_worker_environment,
)
from app.modules.opportunities.source_monitor import NormalizedSourcePayload


def _pdf(*, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("not-available-to-the-converter")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class _Worker:
    def __init__(self, results: list[str]) -> None:
        self.results = results
        self.calls: list[bool] = []

    def convert(self, payload: bytes, *, enable_ocr: bool, limits: DocumentConversionLimits) -> str:
        del payload, limits
        self.calls.append(enable_ocr)
        return self.results.pop(0)


def _converter(worker: _Worker, **overrides: int) -> LayoutAwareDocumentConverter:
    limits = DocumentConversionLimits(
        max_bytes=overrides.get("max_bytes", 100_000),
        max_pages=overrides.get("max_pages", 5),
        max_runtime_seconds=overrides.get("max_runtime_seconds", 5),
        max_output_characters=overrides.get("max_output_characters", 1_000),
        min_text_characters=overrides.get("min_text_characters", 30),
    )
    return LayoutAwareDocumentConverter(limits=limits, worker=worker)


def test_layout_conversion_preserves_docling_markdown_table_without_ocr() -> None:
    table = "# Award\n\n| Route | Deadline |\n| --- | --- |\n| Embassy | 15 May 2027 |\n"
    worker = _Worker([table])

    converted = _converter(worker).convert_pdf(_pdf())

    assert converted.text == table
    assert converted.converter_version == DOCUMENT_CONVERTER_VERSION
    assert converted.page_count == 1
    assert converted.used_ocr is False
    assert worker.calls == [False]


def test_ocr_is_attempted_only_after_measured_text_sufficiency_failure() -> None:
    worker = _Worker(["scan", "OCR eligibility requires citizenship and an application form."])

    converted = _converter(worker).convert_pdf(_pdf(), allow_ocr=True)

    assert converted.used_ocr is True
    assert worker.calls == [False, True]


def test_insufficient_text_fails_closed_without_ocr_attempt() -> None:
    worker = _Worker(["scan"])

    with pytest.raises(DocumentConversionError, match="document_text_insufficient"):
        _converter(worker).convert_pdf(_pdf(), allow_ocr=False)

    assert worker.calls == [False]


def test_ocr_that_remains_insufficient_fails_closed() -> None:
    worker = _Worker(["scan", "still scan"])

    with pytest.raises(DocumentConversionError, match="document_ocr_text_insufficient"):
        _converter(worker).convert_pdf(_pdf(), allow_ocr=True)

    assert worker.calls == [False, True]


def test_converter_rejects_mime_magic_malformed_encrypted_and_oversized_input() -> None:
    worker = _Worker(["unused output that is sufficiently long for the test case"])
    converter = _converter(worker)

    with pytest.raises(DocumentConversionError, match="document_content_type_not_supported"):
        converter.normalize(_pdf(), "text/html")
    with pytest.raises(DocumentConversionError, match="document_content_sniff_mismatch"):
        converter.convert_pdf(b"not a pdf")
    with pytest.raises(DocumentConversionError, match="document_malformed_pdf"):
        converter.convert_pdf(b"%PDF-not-valid")
    with pytest.raises(DocumentConversionError, match="document_encrypted"):
        converter.convert_pdf(_pdf(encrypted=True))
    with pytest.raises(DocumentConversionError, match="document_byte_limit_exceeded"):
        _converter(worker, max_bytes=1).convert_pdf(_pdf())
    assert worker.calls == []


def test_catalogue_normalizer_uses_docling_only_for_pdf() -> None:
    worker = _Worker(["A sufficiently long official document result for normalizer testing."])
    normalizer = CatalogueDocumentPayloadNormalizer(
        converter=_converter(worker),
        allow_ocr=False,
    )

    normalized = normalizer(_pdf(), "application/pdf")

    assert isinstance(normalized, NormalizedSourcePayload)
    assert normalized.text.startswith("A sufficiently")
    assert normalizer.parser_version == DOCUMENT_CONVERTER_VERSION
    assert normalized.parser_version == DOCUMENT_CONVERTER_VERSION
    assert normalized.conversion_metadata == {
        "document_page_count": 1,
        "document_ocr_decision": "not_used",
        "document_ocr_reason": "text_sufficient",
    }
    assert worker.calls == [False]


def test_catalogue_normalizer_records_a_successful_ocr_fallback_per_call() -> None:
    worker = _Worker(["scan", "OCR eligibility requires citizenship and an application form."])
    normalizer = CatalogueDocumentPayloadNormalizer(
        converter=_converter(worker),
        allow_ocr=True,
    )

    normalized = normalizer(_pdf(), "application/pdf")

    assert isinstance(normalized, NormalizedSourcePayload)
    assert normalized.conversion_metadata == {
        "document_page_count": 1,
        "document_ocr_decision": "used",
        "document_ocr_reason": "text_insufficient_ocr_succeeded",
    }
    assert worker.calls == [False, True]


def test_document_worker_environment_removes_application_configuration_and_forces_offline_models(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql://must-not-leak")
    environment = _document_worker_environment(model_artifacts_path="C:/reviewed/docling-models")

    assert "APP_DATABASE_URL" not in environment
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["DOCLING_ARTIFACTS_PATH"] == "C:/reviewed/docling-models"
    assert environment["HOME"] == "C:/reviewed/docling-models"
    assert environment["USERPROFILE"] == "C:/reviewed/docling-models"


def test_docling_timeout_terminates_the_worker_process_tree(monkeypatch) -> None:
    launches: list[dict[str, object]] = []
    taskkill_commands: list[list[str]] = []
    process_group_kills: list[tuple[int, int]] = []

    class TimedOutProcess:
        pid = 4242
        returncode = None

        def communicate(self, *, timeout: int) -> tuple[str, str]:
            del timeout
            raise subprocess.TimeoutExpired("docling", 1)

        def poll(self) -> None:
            return None

        def wait(self, *, timeout: int) -> None:
            del timeout

    process = TimedOutProcess()

    def fake_popen(*_args, **kwargs):
        launches.append(kwargs)
        return process

    def fake_run(command: list[str], **_kwargs):
        taskkill_commands.append(command)
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(document_conversion.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(document_conversion.subprocess, "run", fake_run)
    if document_conversion.os.name != "nt":
        monkeypatch.setattr(document_conversion.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(
            document_conversion.os,
            "killpg",
            lambda process_group, signal: process_group_kills.append((process_group, signal)),
        )

    with pytest.raises(DocumentConversionError, match="document_conversion_timeout"):
        SubprocessDoclingWorker(model_artifacts_path="C:/reviewed/docling-models").convert(
            b"%PDF-test",
            enable_ocr=False,
            limits=DocumentConversionLimits(
                max_bytes=100,
                max_pages=1,
                max_runtime_seconds=1,
                max_output_characters=100,
                min_text_characters=1,
            ),
        )

    assert launches
    assert int(launches[0]["creationflags"]) & getattr(
        document_conversion.subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    if document_conversion.os.name == "nt":
        assert taskkill_commands == [["taskkill", "/PID", "4242", "/T", "/F"]]
    else:
        assert taskkill_commands == []
        assert process_group_kills == [(4242, document_conversion.signal.SIGKILL)]
