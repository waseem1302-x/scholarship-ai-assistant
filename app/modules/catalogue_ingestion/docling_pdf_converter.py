"""Docling PDF converter for structured, layout-aware scholarship guideline extraction.

This module provides high-accuracy PDF-to-Markdown conversion using Docling's layout and
TableFormer models, preserving complex multi-column scholarship tables, stipend tiers, and
document lists while falling back gracefully when unavailable.
"""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.modules.opportunities.source_monitor import SourceFetchError

logger = logging.getLogger(__name__)

DOCLING_CONVERTER_VERSION = "catalogue-docling-pdf.v1"
_MAX_COORDINATES = 2_000
_DOCLING_SEMAPHORE = threading.BoundedSemaphore(value=2)
_DOCLING_THREAD_LOCAL = threading.local()


@dataclass(frozen=True, slots=True)
class ConvertedDoclingResult:
    text: str
    coordinates: tuple[dict[str, Any], ...] = ()
    pages_count: int = 0
    tables_count: int = 0
    converter_version: str = DOCLING_CONVERTER_VERSION


class DoclingConversionError(SourceFetchError):
    """Raised when Docling parsing cannot complete and should fallback."""


def is_docling_available() -> bool:
    """Return True if Docling and its core dependencies are importable and functional."""
    try:
        from docling.document_converter import DocumentConverter  # noqa: F401
        from docling_core.types.doc.document import DoclingDocument  # noqa: F401

        return True
    except (ImportError, OSError, Exception):
        return False


def convert_pdf_docling(
    payload: bytes,
    *,
    models_dir: str | Path | None = ".docling-models",
    table_mode: str = "fast",
    do_ocr: bool = True,
    max_pages: int = 200,
) -> ConvertedDoclingResult:
    """Convert a PDF payload into structured Markdown using Docling.

    Args:
        payload: The raw bytes of the PDF file.
        models_dir: Path to offline model directory (defaults to .docling-models).
        table_mode: "fast" for high throughput or "accurate" for maximum table fidelity.
        do_ocr: Whether to run OCR on non-vector/image pages.
        max_pages: Hard ceiling on total pages to prevent resource exhaustion.

    Returns:
        ConvertedDoclingResult containing markdown text and coordinate metadata.

    Raises:
        SourceFetchError: If the PDF exceeds size/page limits or is malformed.
        DoclingConversionError: If Docling is unavailable or fails to convert.
    """
    if not is_docling_available():
        raise DoclingConversionError("docling_is_unavailable")

    acquired = _DOCLING_SEMAPHORE.acquire(timeout=60.0)
    if not acquired:
        raise DoclingConversionError("docling_worker_pool_busy")

    try:
        from docling.datamodel.base_models import DocumentStream, InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TableFormerMode,
            TableStructureOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        mode = (
            TableFormerMode.FAST
            if str(table_mode).casefold() == "fast"
            else TableFormerMode.ACCURATE
        )
        models_path = (
            Path(models_dir).resolve() if models_dir and Path(models_dir).is_dir() else None
        )
        converter_key = (str(models_path or ""), mode.value, do_ocr)
        converter = getattr(_DOCLING_THREAD_LOCAL, "converter", None)
        if getattr(_DOCLING_THREAD_LOCAL, "converter_key", None) != converter_key:
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = do_ocr
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options = TableStructureOptions(mode=mode)
            if models_path is not None:
                pipeline_options.artifacts_path = str(models_path)
            format_options = {InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            converter = DocumentConverter(format_options=format_options)
            _DOCLING_THREAD_LOCAL.converter = converter
            _DOCLING_THREAD_LOCAL.converter_key = converter_key
        doc_stream = DocumentStream(name="scholarship.pdf", stream=io.BytesIO(payload))
        conv_result = converter.convert(doc_stream)

        doc = conv_result.document
        pages_count = len(getattr(doc, "pages", [])) if hasattr(doc, "pages") else 1
        if pages_count > max_pages:
            raise SourceFetchError("unsupported_or_oversized_source_pdf")

        markdown_text = doc.export_to_markdown()

        coordinates: list[dict[str, Any]] = []
        if hasattr(doc, "pages") and doc.pages:
            for page_no in doc.pages:
                if len(coordinates) < _MAX_COORDINATES:
                    coordinates.append({"page": int(page_no)})

        tables_count = len(getattr(doc, "tables", [])) if hasattr(doc, "tables") else 0

        return ConvertedDoclingResult(
            text=markdown_text.strip(),
            coordinates=tuple(coordinates),
            pages_count=pages_count,
            tables_count=tables_count,
        )
    except SourceFetchError:
        raise
    except Exception as exc:
        logger.warning("Docling PDF conversion failed, fallback required: %s", exc)
        raise DoclingConversionError(f"docling_conversion_failed: {exc}") from exc
    finally:
        _DOCLING_SEMAPHORE.release()
