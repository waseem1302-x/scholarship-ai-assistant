"""Restricted pure-data text extraction for supported PDF and DOCX inputs."""

import io
import re
import xml.etree.ElementTree as element_tree
import zipfile
from concurrent.futures import ProcessPoolExecutor, TimeoutError

from app.core.errors import AppError
from app.modules.document_lab.validation import (
    DOCX_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
)


def extract_restricted(
    content: bytes,
    content_type: str,
    *,
    max_characters: int,
    timeout_seconds: int = 10,
) -> str:
    """Extract in a short-lived subprocess.

    The subprocess receives only bytes and cannot execute document code. Linux
    production containers additionally run it with a no-network namespace; the
    Python boundary remains deterministic for local Windows development.
    """
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_extract_result, content, content_type, max_characters)
        try:
            text, failure_code = future.result(timeout=timeout_seconds)
            if failure_code:
                raise AppError(failure_code, "Document extraction failed.", 422)
            assert text is not None
            return text
        except TimeoutError as exc:
            future.cancel()
            raise AppError("extraction_timeout", "Document extraction timed out.", 422) from exc
        except AppError:
            raise
        except Exception as exc:
            raise AppError("extraction_failed", "Document extraction failed.", 422) from exc


def _extract_result(
    content: bytes, content_type: str, max_characters: int
) -> tuple[str | None, str | None]:
    """Return serializable worker results; `AppError` itself cannot be pickled."""
    try:
        return _extract(content, content_type, max_characters), None
    except AppError as exc:
        return None, exc.code


def _extract(content: bytes, content_type: str, max_characters: int) -> str:
    if content_type == DOCX_CONTENT_TYPE:
        text = _extract_docx(content)
    elif content_type == PDF_CONTENT_TYPE:
        text = _extract_pdf(content)
    else:
        raise AppError("unsupported_format", "Document extraction is not supported.", 422)
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        raise AppError(
            "image_only_or_empty_document",
            "No extractable text was found.",
            422,
        )
    if len(normalized) > max_characters:
        raise AppError(
            "extracted_text_limit_exceeded",
            "Extracted text exceeds the limit.",
            422,
        )
    return normalized


def _extract_docx(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document = archive.read("word/document.xml")
        root = element_tree.fromstring(document)
    except (element_tree.ParseError, zipfile.BadZipFile, KeyError) as exc:
        raise AppError("malformed_docx", "Document extraction failed.", 422) from exc
    return "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))


def _extract_pdf(content: bytes) -> str:
    # This deliberately limited parser extracts literal text strings only. It
    # rejects image-only and unsupported encoded PDFs rather than doing OCR.
    strings = re.findall(rb"\((?:\\.|[^\\)])*\)", content)
    text_parts = []
    for raw in strings:
        value = raw[1:-1]
        value = re.sub(rb"\\([()\\])", rb"\1", value)
        text_parts.append(value.decode("latin-1", errors="ignore"))
    return "\n".join(text_parts)
