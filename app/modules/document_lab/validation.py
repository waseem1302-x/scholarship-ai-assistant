"""Byte-level document validation. Never trust browser extensions or MIME."""

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

from app.core.errors import AppError

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_CONTENT_TYPES = {PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE}
MAX_ZIP_ENTRIES = 1_000
MAX_ZIP_EXPANSION_RATIO = 100


@dataclass(frozen=True)
class ValidatedDocument:
    detected_content_type: str
    page_count: int | None


def validate_upload(
    *,
    filename: str,
    declared_content_type: str,
    content: bytes,
    max_bytes: int,
    max_pages: int,
) -> ValidatedDocument:
    if not filename or len(filename) > 255:
        raise _rejected("invalid_filename")
    if len(content) > max_bytes:
        raise _rejected("file_too_large")
    if not content:
        raise _rejected("empty_file")
    suffix = PurePath(filename).suffix.casefold()
    declared = declared_content_type.split(";", maxsplit=1)[0].strip().casefold()
    if suffix not in {".pdf", ".docx"} or declared not in ALLOWED_CONTENT_TYPES:
        raise _rejected("unsupported_format")
    if suffix == ".pdf":
        return _validate_pdf(declared, content, max_pages)
    return _validate_docx(declared, content)


def _validate_pdf(declared: str, content: bytes, max_pages: int) -> ValidatedDocument:
    if declared != PDF_CONTENT_TYPE or not content.startswith(b"%PDF-"):
        raise _rejected("mime_or_magic_mismatch")
    # Password-protected PDFs must never reach a parser or provider.
    if re.search(rb"/Encrypt\b", content):
        raise _rejected("password_protected_document")
    if b"%%EOF" not in content[-2_048:]:
        raise _rejected("malformed_pdf")
    page_count = len(re.findall(rb"/Type\s*/Page\b", content))
    if page_count <= 0:
        raise _rejected("image_only_or_malformed_pdf")
    if page_count > max_pages:
        raise _rejected("page_limit_exceeded")
    return ValidatedDocument(detected_content_type=PDF_CONTENT_TYPE, page_count=page_count)


def _validate_docx(declared: str, content: bytes) -> ValidatedDocument:
    if declared != DOCX_CONTENT_TYPE or not content.startswith(b"PK\x03\x04"):
        raise _rejected("mime_or_magic_mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = {entry.filename.casefold() for entry in entries}
            if len(entries) > MAX_ZIP_ENTRIES or "[content_types].xml" not in names:
                raise _rejected("malformed_docx")
            if "word/document.xml" not in names:
                raise _rejected("malformed_docx")
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise _rejected("password_protected_document")
            if any(
                "vbaproject.bin" in name or name.endswith((".zip", ".rar", ".7z")) for name in names
            ):
                raise _rejected("macro_or_archive_document")
            compressed = sum(max(entry.compress_size, 1) for entry in entries)
            expanded = sum(entry.file_size for entry in entries)
            if expanded > compressed * MAX_ZIP_EXPANSION_RATIO:
                raise _rejected("zip_bomb_suspected")
            if expanded > 100_000_000:
                raise _rejected("zip_bomb_suspected")
            archive.read("word/document.xml")
    except zipfile.BadZipFile as exc:
        raise _rejected("malformed_docx") from exc
    return ValidatedDocument(detected_content_type=DOCX_CONTENT_TYPE, page_count=None)


def _rejected(code: str) -> AppError:
    return AppError(code, "The uploaded file cannot be accepted.", 422)
