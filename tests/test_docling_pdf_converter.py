"""Unit tests for Docling PDF converter integration and safe fallback mechanics."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from pypdf import PageObject, PdfWriter

from app.modules.catalogue_ingestion.acquisition_fetcher import (
    _convert_pdf,
    convert_catalogue_payload,
)
from app.modules.catalogue_ingestion.docling_pdf_converter import (
    ConvertedDoclingResult,
    DoclingConversionError,
    convert_pdf_docling,
    is_docling_available,
)


def _create_minimal_pdf_bytes(text: str = "Scholarship guidelines for 2027.") -> bytes:
    """Helper to create a valid minimal PDF in memory."""
    writer = PdfWriter()
    page = PageObject.create_blank_page(width=612, height=792)
    writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_is_docling_available_returns_bool() -> None:
    result = is_docling_available()
    assert isinstance(result, bool)


def test_convert_pdf_docling_raises_when_unavailable() -> None:
    with (
        patch(
            "app.modules.catalogue_ingestion.docling_pdf_converter.is_docling_available",
            return_value=False,
        ),
        pytest.raises(DoclingConversionError, match="docling_is_unavailable"),
    ):
        convert_pdf_docling(b"%PDF-1.4 dummy content")


def test_convert_pdf_fallback_to_pypdf_when_docling_fails() -> None:
    pdf_bytes = _create_minimal_pdf_bytes("Fallback scholarship text")
    with (
        patch(
            "app.modules.catalogue_ingestion.docling_pdf_converter.convert_pdf_docling",
            side_effect=DoclingConversionError("mocked_error"),
        ),
        patch(
            "app.modules.catalogue_ingestion.docling_pdf_converter.is_docling_available",
            return_value=True,
        ),
    ):
        converted = _convert_pdf(pdf_bytes, prefer_docling=True)
        assert converted is not None
        assert isinstance(converted.text, str)


def test_convert_pdf_uses_docling_when_available() -> None:
    pdf_bytes = _create_minimal_pdf_bytes()
    mock_result = ConvertedDoclingResult(
        text=(
            "# Scholarship Programme 2027\n\n"
            "| Category | Stipend |\n"
            "| --- | --- |\n"
            "| Research | JPY 144,000 |"
        ),
        coordinates=({"page": 1},),
        pages_count=1,
        tables_count=1,
    )
    with (
        patch(
            "app.modules.catalogue_ingestion.docling_pdf_converter.is_docling_available",
            return_value=True,
        ),
        patch(
            "app.modules.catalogue_ingestion.docling_pdf_converter.convert_pdf_docling",
            return_value=mock_result,
        ),
    ):
        converted = _convert_pdf(pdf_bytes, prefer_docling=True)
        assert "Scholarship Programme 2027" in converted.text
        assert "| Research | JPY 144,000 |" in converted.text
        assert converted.coordinates == ({"page": 1},)


def test_convert_catalogue_payload_routes_pdf_correctly() -> None:
    pdf_bytes = _create_minimal_pdf_bytes()
    mock_result = ConvertedDoclingResult(
        text="Official MEXT Guidelines",
        coordinates=({"page": 1},),
        pages_count=1,
    )
    with (
        patch(
            "app.modules.catalogue_ingestion.docling_pdf_converter.is_docling_available",
            return_value=True,
        ),
        patch(
            "app.modules.catalogue_ingestion.docling_pdf_converter.convert_pdf_docling",
            return_value=mock_result,
        ),
    ):
        converted = convert_catalogue_payload(
            pdf_bytes,
            content_type="application/pdf",
            final_url="https://studyinjapan.go.jp/guidelines.pdf",
        )
        assert "Official MEXT Guidelines" in converted.text
