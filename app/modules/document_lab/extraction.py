"""Restricted pure-data text extraction for supported PDF and DOCX inputs."""

import io
import xml.etree.ElementTree as element_tree
import zipfile

from app.core.errors import AppError
from app.modules.document_lab.process_sandbox import (
    BoundedProcessFailed,
    BoundedProcessTimeout,
    run_bounded_process,
)
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
    """Extract in a fresh parser process with a hard parent-owned deadline.

    The child receives only document bytes and deterministic configuration. If
    it exceeds the wall-clock deadline, the parent terminates/kills the concrete
    process before returning. POSIX children also receive CPU, memory, file-
    descriptor, output-size, and core-dump limits.

    Production keeps Document Lab disabled unless deployment-level parser
    isolation (including no-network and restricted filesystem controls) has
    separately been approved and enabled.
    """

    try:
        text, failure_code = run_bounded_process(
            _extract_result,
            (content, content_type, max_characters),
            timeout_seconds=timeout_seconds,
        )
    except BoundedProcessTimeout as exc:
        raise AppError("extraction_timeout", "Document extraction timed out.", 422) from exc
    except BoundedProcessFailed as exc:
        raise AppError("extraction_failed", "Document extraction failed.", 422) from exc

    if failure_code:
        raise AppError(failure_code, "Document extraction failed.", 422)
    assert text is not None
    return text


def _extract_result(
    content: bytes, content_type: str, max_characters: int
) -> tuple[str | None, str | None]:
    """Return serializable worker results; `AppError` itself is not transported."""

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
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise AppError("pdf_parser_unavailable", "Document extraction failed.", 422) from exc
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise AppError("password_protected_document", "Document extraction failed.", 422)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except AppError:
        raise
    except Exception as exc:
        raise AppError("malformed_pdf", "Document extraction failed.", 422) from exc
