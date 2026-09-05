"""Catalogue acquisition fetcher using the existing SSRF/robots/redirect safety boundary.

This adapter extends the source-monitor transport with bounded parsing for sitemap/XML, CSV, DOCX,
and XLSX while preserving the same URL, DNS/IP, peer-address, redirect, robots, timeout, and byte
controls. Image-like inputs and textless PDFs are never OCR'd here; they return an explicit OCR
escalation signal for a separately reviewed OCR capability.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from typing import Any
from xml.etree import ElementTree

from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SafeSourceFetcher,
    SourceFetchError,
    extract_evidence_section,
    is_authentication_destination,
    validate_monitor_url,
    validate_response_peer,
)

CATALOGUE_CONVERSION_VERSION = "catalogue-acquisition-conversion.v1"
_MAX_ARCHIVE_ENTRIES = 5_000
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 50_000_000
_MAX_DOCX_PARAGRAPHS = 20_000
_MAX_XLSX_SHEETS = 50
_MAX_XLSX_CELLS = 100_000
_MAX_SITEMAP_LINKS = 5_000
_MAX_COORDINATES = 2_000

_HTML_TYPES = {"text/html", "application/xhtml+xml"}
_XML_TYPES = {"application/xml", "text/xml", "application/rss+xml", "application/atom+xml"}
_CSV_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}
_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_IMAGE_TYPES = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
_ACCEPTED_TYPES = {
    "application/pdf",
    "text/calendar",
    "text/plain",
    *_HTML_TYPES,
    *_XML_TYPES,
    *_CSV_TYPES,
    _DOCX_TYPE,
    _XLSX_TYPE,
    *_IMAGE_TYPES,
    "application/octet-stream",
    "application/zip",
}


@dataclass(frozen=True)
class StructuredFetchedLink(FetchedLink):
    relation: tuple[str, ...] = ()
    hreflang: str | None = None
    media_type: str | None = None
    context_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogueFetchedSource(FetchedSource):
    original_artifact_hash: str | None = None
    sniffed_content_type: str | None = None
    conversion_version: str | None = CATALOGUE_CONVERSION_VERSION
    coordinates: tuple[dict[str, Any], ...] = ()
    canonical_url_hint: str | None = None
    language_hints: tuple[str, ...] = ()


class CatalogueSafeSourceFetcher(SafeSourceFetcher):
    """Safely fetch official catalogue material and normalize supported static formats."""

    def fetch(self, url: str) -> FetchedSource:
        return self.fetch_with_limit(url, max_bytes=self.policy_for(url).max_bytes)

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        if max_bytes < 1:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        validate_monitor_url(url)
        policy = self.policy_for(url)
        effective_max = min(policy.max_bytes, max_bytes)
        self._assert_robots_allowed(url, policy)
        request = urllib.request.Request(url, headers={"User-Agent": policy.user_agent})
        try:
            with self.opener.open(request, timeout=policy.timeout_seconds) as response:
                final_url = response.geturl()
                validate_monitor_url(final_url)
                validate_response_peer(response)
                if is_authentication_destination(final_url):
                    raise SourceFetchError("source_authentication_required")
                declared_type = response.headers.get_content_type().casefold()
                if declared_type not in _ACCEPTED_TYPES:
                    raise SourceFetchError(
                        f"unsupported_source_content_type: {declared_type[:100]}"
                    )
                payload = response.read(effective_max + 1)
        except SourceFetchError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise SourceFetchError("source_rate_limited: http_429") from exc
            if 400 <= exc.code <= 499:
                raise SourceFetchError(f"source_access_denied: http_{exc.code}") from exc
            if 500 <= exc.code <= 599:
                raise SourceFetchError(f"source_unreachable: http_{exc.code}") from exc
            raise SourceFetchError(f"source_http_error: http_{exc.code}") from exc
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise SourceFetchError(f"source_fetch_failed: {type(exc).__name__}") from exc

        if len(payload) > effective_max:
            if effective_max < policy.max_bytes:
                raise SourceFetchError("crawl_byte_budget_exceeded")
            raise SourceFetchError(f"source_too_large: exceeded {policy.max_bytes} bytes")

        original_hash = hashlib.sha256(payload).hexdigest()
        sniffed_type = sniff_catalogue_mime(payload, declared_type=declared_type, url=final_url)
        if declared_type not in {"application/octet-stream", "application/zip"}:
            _reject_material_mime_mismatch(declared_type, sniffed_type)
        if sniffed_type in _IMAGE_TYPES:
            raise SourceFetchError(f"source_requires_ocr: {sniffed_type}")

        conversion = convert_catalogue_payload(
            payload,
            content_type=sniffed_type,
            final_url=final_url,
        )
        text = conversion.text.strip()
        if sniffed_type == "application/pdf" and (
            conversion.requires_ocr or len(" ".join(text.split())) < 20
        ):
            raise SourceFetchError("source_requires_ocr: textless_or_scanned_pdf")
        if len(" ".join(text.split())) < 20 and sniffed_type not in _XML_TYPES:
            raise SourceFetchError("source_has_no_extractable_evidence")

        section = extract_evidence_section(text) if text else None
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        return CatalogueFetchedSource(
            url=url,
            final_url=final_url,
            content_hash=content_hash,
            excerpt_text=(section.text[:500] if section else text[:500] or None),
            section_label=section.label if section else None,
            bytes_read=len(payload),
            normalized_text=text,
            normalized_content_hash=content_hash,
            content_type=sniffed_type,
            links=conversion.links,
            original_artifact_hash=original_hash,
            sniffed_content_type=sniffed_type,
            conversion_version=CATALOGUE_CONVERSION_VERSION,
            coordinates=conversion.coordinates,
            canonical_url_hint=conversion.canonical_url_hint,
            language_hints=conversion.language_hints,
        )


@dataclass(frozen=True, slots=True)
class _ConvertedPayload:
    text: str
    links: tuple[StructuredFetchedLink, ...] = ()
    coordinates: tuple[dict[str, Any], ...] = ()
    canonical_url_hint: str | None = None
    language_hints: tuple[str, ...] = ()
    page_count: int = 0
    text_page_count: int = 0
    requires_ocr: bool = False


def sniff_catalogue_mime(payload: bytes, *, declared_type: str, url: str) -> str:
    head = payload[:512].lstrip()
    lowered_path = urllib.parse.urlparse(url).path.casefold()
    if payload.startswith(b"%PDF-"):
        return "application/pdf"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if payload.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if payload.startswith(b"BM"):
        return "image/bmp"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image/webp"
    if payload.startswith(b"PK\x03\x04"):
        detected = _sniff_ooxml_type(payload)
        return detected or declared_type
    if head.startswith(b"<"):
        prefix = head[:256].lower()
        if b"<html" in prefix or b"<!doctype html" in prefix:
            return "text/html"
        if lowered_path.endswith((".xml", ".rss", ".atom")) or declared_type in _XML_TYPES:
            return "application/xml"
    if lowered_path.endswith(".csv") or declared_type in _CSV_TYPES:
        return "text/csv"
    return declared_type


def convert_catalogue_payload(
    payload: bytes,
    *,
    content_type: str,
    final_url: str,
) -> _ConvertedPayload:
    if content_type in _HTML_TYPES:
        return _convert_html(payload, final_url=final_url)
    if content_type in _XML_TYPES:
        return _convert_xml(payload, final_url=final_url)
    if content_type in {"text/plain", "text/calendar"}:
        return _ConvertedPayload(_normalize_text(payload.decode("utf-8", errors="ignore")))
    if content_type == "text/csv":
        return _convert_csv(payload)
    if content_type == _DOCX_TYPE:
        return _convert_docx(payload)
    if content_type == _XLSX_TYPE:
        return _convert_xlsx(payload)
    if content_type == "application/pdf":
        return _convert_pdf(payload)
    raise SourceFetchError(f"unsupported_source_content_type: {content_type[:100]}")


def _reject_material_mime_mismatch(declared: str, sniffed: str) -> None:
    compatible = {
        ("application/xhtml+xml", "text/html"),
        ("text/xml", "application/xml"),
        ("application/xml", "application/xml"),
        ("application/rss+xml", "application/xml"),
        ("application/atom+xml", "application/xml"),
        ("application/vnd.ms-excel", "text/csv"),
        ("application/csv", "text/csv"),
    }
    if declared == sniffed or (declared, sniffed) in compatible:
        return
    if declared.startswith("text/") and sniffed.startswith("text/"):
        return
    raise SourceFetchError(f"source_mime_mismatch: {declared} -> {sniffed}")


def _sniff_ooxml_type(payload: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return None
    if "word/document.xml" in names:
        return _DOCX_TYPE
    if "xl/workbook.xml" in names:
        return _XLSX_TYPE
    return None


class _StructuredHTMLParser(HTMLParser):
    def __init__(self, *, base_url: str, max_links: int = 2_000) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.max_links = max_links
        self.links: list[StructuredFetchedLink] = []
        self.text_parts: list[str] = []
        self._contexts: list[str] = []
        self._href: str | None = None
        self._title: str | None = None
        self._rel: tuple[str, ...] = ()
        self._hreflang: str | None = None
        self._media_type: str | None = None
        self._anchor_text: list[str] = []
        self.canonical_url: str | None = None
        self.languages: set[str] = set()
        self._ignored_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
            return
        values = {key.casefold(): (value or "") for key, value in attrs}
        if tag in {"table", "thead", "tbody", "tr", "td", "th", "main", "article", "nav"}:
            self._contexts.append(tag)
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section"}:
            self.text_parts.append("\n")
        lang = (values.get("lang") or "").strip()
        if lang:
            self.languages.add(lang[:40])
        if len(self.links) >= self.max_links:
            return
        if tag == "link":
            href = (values.get("href") or "").strip()
            if not href:
                return
            rel = tuple(item for item in (values.get("rel") or "").casefold().split() if item)
            resolved = urllib.parse.urljoin(self.base_url, href)
            hreflang = (values.get("hreflang") or "").strip() or None
            media_type = (values.get("type") or "").strip().casefold() or None
            self.links.append(
                StructuredFetchedLink(
                    url=resolved,
                    title=(values.get("title") or "").strip()[:500] or None,
                    relation=rel,
                    hreflang=hreflang,
                    media_type=media_type,
                    context_tags=tuple(self._contexts[-4:]),
                )
            )
            if "canonical" in rel:
                self.canonical_url = resolved
            if hreflang:
                self.languages.add(hreflang[:40])
            return
        if tag != "a":
            return
        href = (values.get("href") or "").strip()
        if not href:
            return
        self._href = href
        self._title = (values.get("title") or "").strip()[:500] or None
        self._rel = tuple(item for item in (values.get("rel") or "").casefold().split() if item)
        self._hreflang = (values.get("hreflang") or "").strip() or None
        self._media_type = (values.get("type") or "").strip().casefold() or None
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        self.text_parts.append(data)
        if self._href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if tag == "a" and self._href is not None and len(self.links) < self.max_links:
            resolved = urllib.parse.urljoin(self.base_url, self._href)
            text = " ".join(" ".join(self._anchor_text).split())[:500]
            self.links.append(
                StructuredFetchedLink(
                    url=resolved,
                    text=text,
                    title=self._title,
                    relation=self._rel,
                    hreflang=self._hreflang,
                    media_type=self._media_type,
                    context_tags=tuple(self._contexts[-4:]),
                )
            )
            if self._hreflang:
                self.languages.add(self._hreflang[:40])
            self._href = None
            self._title = None
            self._rel = ()
            self._hreflang = None
            self._media_type = None
            self._anchor_text = []
        if tag in self._contexts:
            for index in range(len(self._contexts) - 1, -1, -1):
                if self._contexts[index] == tag:
                    del self._contexts[index]
                    break


def _decode_html_payload(payload: bytes) -> str:
    """Decode raw HTML bytes with charset detection and global language fallbacks."""
    # 1. Check <meta charset="..."> or <meta http-equiv="Content-Type" ...> in first 2048 bytes
    head_prefix = payload[:2048].decode("ascii", errors="ignore")
    meta_match = re.search(r"<meta[^>]+charset=['\"]?([a-zA-Z0-9_-]+)", head_prefix, re.IGNORECASE)
    if meta_match:
        charset = meta_match.group(1).strip().lower()
        try:
            return payload.decode(charset)
        except (UnicodeDecodeError, LookupError):
            pass

    # 2. Try UTF-8 (covers modern web and most UTF-8-BOM)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # 3. Try common global scholarship country charsets
    for candidate in (
        "shift_jis",
        "gb18030",
        "euc_jp",
        "euc_kr",
        "big5",
        "windows-1252",
        "iso-8859-1",
    ):
        try:
            return payload.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue

    # 4. Fallback
    return payload.decode("utf-8", errors="replace")


def _convert_html(payload: bytes, *, final_url: str) -> _ConvertedPayload:
    parser = _StructuredHTMLParser(base_url=final_url)
    try:
        decoded_text = _decode_html_payload(payload)
        parser.feed(decoded_text)
        parser.close()
    except Exception as exc:
        raise SourceFetchError("malformed_source_html") from exc
    text = _normalize_text(" ".join(parser.text_parts))
    return _ConvertedPayload(
        text=text,
        links=tuple(parser.links),
        canonical_url_hint=parser.canonical_url,
        language_hints=tuple(sorted(parser.languages)),
    )


def _convert_xml(payload: bytes, *, final_url: str) -> _ConvertedPayload:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise SourceFetchError("malformed_source_xml") from exc
    locations: list[str] = []
    text_parts: list[str] = []
    for element in root.iter():
        value = (element.text or "").strip()
        if not value:
            continue
        local_name = element.tag.rsplit("}", 1)[-1].casefold()
        if local_name == "loc" and len(locations) < _MAX_SITEMAP_LINKS:
            resolved = urllib.parse.urljoin(final_url, value)
            locations.append(resolved)
        else:
            text_parts.append(value)
    links = tuple(
        StructuredFetchedLink(
            url=value,
            relation=("sitemap",),
            context_tags=("sitemap",),
        )
        for value in locations
    )
    return _ConvertedPayload(
        text=_normalize_text("\n".join([*text_parts, *locations])),
        links=links,
    )


def _convert_csv(payload: bytes) -> _ConvertedPayload:
    decoded = payload.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(decoded))
    rows: list[str] = []
    coordinates: list[dict[str, Any]] = []
    for row_index, row in enumerate(reader, start=1):
        if row_index > 50_000:
            raise SourceFetchError("oversized_source_csv")
        values = [" ".join(value.split())[:10_000] for value in row[:500]]
        rows.append(" | ".join(values))
        if len(coordinates) < _MAX_COORDINATES:
            coordinates.append({"row": row_index, "columns": len(values)})
    return _ConvertedPayload(
        text=_normalize_text("\n".join(rows)),
        coordinates=tuple(coordinates),
    )


def _convert_docx(payload: bytes) -> _ConvertedPayload:
    with _bounded_zip(payload) as archive:
        try:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
        except KeyError as exc:
            raise SourceFetchError("malformed_source_docx") from exc
        except ElementTree.ParseError as exc:
            raise SourceFetchError("malformed_source_docx") from exc
        paragraphs: list[str] = []
        coordinates: list[dict[str, Any]] = []
        for paragraph_index, paragraph in enumerate(
            (item for item in document.iter() if item.tag.rsplit("}", 1)[-1] == "p"),
            start=1,
        ):
            if paragraph_index > _MAX_DOCX_PARAGRAPHS:
                raise SourceFetchError("oversized_source_docx")
            text = "".join(
                child.text or ""
                for child in paragraph.iter()
                if child.tag.rsplit("}", 1)[-1] in {"t", "tab", "br"}
            ).strip()
            if not text:
                continue
            paragraphs.append(text)
            if len(coordinates) < _MAX_COORDINATES:
                coordinates.append({"paragraph": paragraph_index})
        return _ConvertedPayload(
            text=_normalize_text("\n".join(paragraphs)),
            coordinates=tuple(coordinates),
        )


def _convert_xlsx(payload: bytes) -> _ConvertedPayload:
    with _bounded_zip(payload) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        worksheet_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        if len(worksheet_names) > _MAX_XLSX_SHEETS:
            raise SourceFetchError("oversized_source_xlsx")
        rows: list[str] = []
        coordinates: list[dict[str, Any]] = []
        cell_count = 0
        for sheet_index, name in enumerate(worksheet_names, start=1):
            try:
                root = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError as exc:
                raise SourceFetchError("malformed_source_xlsx") from exc
            for cell in (item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "c"):
                cell_count += 1
                if cell_count > _MAX_XLSX_CELLS:
                    raise SourceFetchError("oversized_source_xlsx")
                reference = cell.attrib.get("r", "")[:30]
                cell_type = cell.attrib.get("t", "")
                raw_value = next(
                    (
                        child.text
                        for child in cell
                        if child.tag.rsplit("}", 1)[-1] in {"v", "t"} and child.text is not None
                    ),
                    "",
                )
                value = raw_value
                if cell_type == "s" and raw_value.isdigit():
                    index = int(raw_value)
                    if 0 <= index < len(shared_strings):
                        value = shared_strings[index]
                if not value:
                    continue
                rows.append(f"sheet {sheet_index} {reference}: {value}")
                if len(coordinates) < _MAX_COORDINATES:
                    coordinates.append({"sheet": sheet_index, "cell": reference})
        return _ConvertedPayload(
            text=_normalize_text("\n".join(rows)),
            coordinates=tuple(coordinates),
        )


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except ElementTree.ParseError as exc:
        raise SourceFetchError("malformed_source_xlsx") from exc
    values: list[str] = []
    for item in root:
        values.append(
            "".join(
                child.text or "" for child in item.iter() if child.tag.rsplit("}", 1)[-1] == "t"
            )
        )
    return values


def _convert_pdf_pypdf(payload: bytes) -> _ConvertedPayload:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload), strict=True)
        if reader.is_encrypted or len(reader.pages) > 200:
            raise SourceFetchError("unsupported_or_oversized_source_pdf")
        pages: list[str] = []
        coordinates: list[dict[str, Any]] = []
        text_page_count = 0
        for page_number, page in enumerate(reader.pages, start=1):
            value = page.extract_text() or ""
            pages.append(value)
            if value.strip() and len(coordinates) < _MAX_COORDINATES:
                coordinates.append({"page": page_number})
            if len(value.split()) >= 10:
                text_page_count += 1
        return _ConvertedPayload(
            text=_normalize_text("\n".join(pages)),
            coordinates=tuple(coordinates),
            page_count=len(reader.pages),
            text_page_count=text_page_count,
        )
    except SourceFetchError:
        raise
    except Exception as exc:
        raise SourceFetchError("malformed_source_pdf") from exc


def _convert_pdf(payload: bytes, *, prefer_docling: bool = True) -> _ConvertedPayload:
    native: _ConvertedPayload | None = None
    native_error: SourceFetchError | None = None
    try:
        native = _convert_pdf_pypdf(payload)
    except SourceFetchError as exc:
        native_error = exc

    if native is not None and _native_pdf_text_is_sufficient(native):
        return native

    if prefer_docling:
        try:
            from app.core.config import get_settings
            from app.modules.catalogue_ingestion.docling_pdf_converter import (
                DoclingConversionError,
                convert_pdf_docling,
                is_docling_available,
            )

            settings = get_settings()
            if settings.catalogue_docling_enabled and is_docling_available():
                result = convert_pdf_docling(
                    payload,
                    models_dir=settings.catalogue_docling_models_dir,
                    table_mode=settings.catalogue_docling_table_mode,
                    do_ocr=settings.catalogue_docling_do_ocr,
                )
                if result.text:
                    return _ConvertedPayload(
                        text=_normalize_text(result.text),
                        coordinates=result.coordinates,
                        page_count=result.pages_count,
                        text_page_count=result.pages_count,
                    )
        except DoclingConversionError:
            pass
        except SourceFetchError:
            raise
        except Exception:
            pass

    if native is not None:
        return replace(native, requires_ocr=True)
    assert native_error is not None
    raise native_error


def _native_pdf_text_is_sufficient(converted: _ConvertedPayload) -> bool:
    words = len(converted.text.split())
    if words < 20 or converted.page_count < 1:
        return False
    return converted.text_page_count == converted.page_count


class _BoundedZip:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.archive: zipfile.ZipFile | None = None

    def __enter__(self) -> zipfile.ZipFile:
        try:
            archive = zipfile.ZipFile(io.BytesIO(self.payload))
        except (OSError, zipfile.BadZipFile) as exc:
            raise SourceFetchError("malformed_source_archive") from exc
        infos = archive.infolist()
        if len(infos) > _MAX_ARCHIVE_ENTRIES:
            archive.close()
            raise SourceFetchError("oversized_source_archive")
        total_uncompressed = sum(max(0, info.file_size) for info in infos)
        if total_uncompressed > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            archive.close()
            raise SourceFetchError("oversized_source_archive")
        if any(_unsafe_archive_name(info.filename) for info in infos):
            archive.close()
            raise SourceFetchError("unsafe_source_archive_path")
        self.archive = archive
        return archive

    def __exit__(self, *_: object) -> None:
        if self.archive is not None:
            self.archive.close()


def _bounded_zip(payload: bytes) -> _BoundedZip:
    return _BoundedZip(payload)


def _unsafe_archive_name(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return normalized.startswith("/") or "../" in f"/{normalized}"


def _normalize_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


__all__ = [
    "CATALOGUE_CONVERSION_VERSION",
    "CatalogueFetchedSource",
    "CatalogueSafeSourceFetcher",
    "StructuredFetchedLink",
    "convert_catalogue_payload",
    "sniff_catalogue_mime",
]
