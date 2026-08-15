"""Deterministic seed loaders and parsers; seed material is never authoritative evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.modules.catalogue_ingestion.schemas import SeedCandidate
from app.modules.opportunities.source_monitor import (
    SafeRedirectHandler,
    SourceFetchError,
    validate_monitor_url,
    validate_response_peer,
)

MAX_SEED_BYTES = 25_000_000
MAX_SEED_TEXT_CHARACTERS = 2_000_000
AZURE_STORAGE_SCOPE = "https://storage.azure.com/.default"
URL_PATTERN = re.compile(r"https://[^\s)>\]}]+", re.IGNORECASE)
BULLET_PATTERN = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


class SeedParseError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedSeed:
    label: str
    fingerprint: str
    content: bytes
    content_type: str


class SeedDocumentParser(Protocol):
    def parse(self, document: LoadedSeed) -> list[SeedCandidate]: ...


class SeedSourceLoader:
    """Load an operator-supplied local path or Azure Blob HTTPS URI without persisting secrets."""

    def __init__(self, *, credential: object | None = None) -> None:
        self.credential = credential

    def load(self, source: str) -> LoadedSeed:
        parsed = urllib.parse.urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return self._load_https(source)
        if parsed.scheme and parsed.scheme != "file":
            raise SeedParseError("unsupported_seed_source")
        path = Path(urllib.request.url2pathname(parsed.path) if parsed.scheme == "file" else source)
        if not path.is_file():
            raise SeedParseError("seed_file_not_found")
        if path.stat().st_size > MAX_SEED_BYTES:
            raise SeedParseError("seed_file_too_large")
        content = path.read_bytes()
        return LoadedSeed(
            label=path.name,
            fingerprint=hashlib.sha256(content).hexdigest(),
            content=content,
            content_type=_content_type_from_name(path.name),
        )

    def _load_https(self, source: str) -> LoadedSeed:
        validate_monitor_url(source)
        parsed = urllib.parse.urlparse(source)
        if not (parsed.hostname or "").endswith(".blob.core.windows.net"):
            raise SeedParseError("remote_seed_must_use_azure_blob")
        headers = {"User-Agent": "ScholarshipAI-Seed/0.1"}
        if not parsed.query:
            credential = self.credential or self._default_credential()
            try:
                token = credential.get_token(AZURE_STORAGE_SCOPE).token
            except Exception as exc:
                raise SeedParseError("seed_blob_identity_failed") from exc
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(source, headers=headers)
        opener = urllib.request.build_opener(SafeRedirectHandler)
        try:
            with opener.open(request, timeout=20) as response:
                validate_response_peer(response)
                final = urllib.parse.urlparse(response.geturl())
                if not (final.hostname or "").endswith(".blob.core.windows.net"):
                    raise SeedParseError("remote_seed_redirected_outside_azure_blob")
                content = response.read(MAX_SEED_BYTES + 1)
                content_type = response.headers.get_content_type()
        except (TimeoutError, OSError, urllib.error.URLError, SourceFetchError) as exc:
            raise SeedParseError("seed_fetch_failed") from exc
        if len(content) > MAX_SEED_BYTES:
            raise SeedParseError("seed_file_too_large")
        # Query parameters may contain a SAS token and are deliberately omitted.
        label = Path(parsed.path).name or "azure-blob-seed"
        return LoadedSeed(
            label=label,
            fingerprint=hashlib.sha256(content).hexdigest(),
            content=content,
            content_type=content_type or _content_type_from_name(label),
        )

    @staticmethod
    def _default_credential() -> object:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise SeedParseError("azure_identity_unavailable") from exc
        return DefaultAzureCredential()


class LocalSeedDocumentParser:
    def parse(self, document: LoadedSeed) -> list[SeedCandidate]:
        content_type = document.content_type.casefold()
        name = document.label.casefold()
        if content_type == "application/pdf" or name.endswith(".pdf"):
            text = self._pdf_text(document.content)
            return self._parse_text(text)
        text = document.content.decode("utf-8-sig", errors="strict")
        if len(text) > MAX_SEED_TEXT_CHARACTERS:
            raise SeedParseError("seed_text_too_large")
        if content_type == "application/json" or name.endswith((".json", ".jsonl")):
            return self._parse_json(text, json_lines=name.endswith(".jsonl"))
        if name.endswith((".csv", ".tsv")) or content_type in {
            "text/csv",
            "text/tab-separated-values",
        }:
            return self._parse_csv(text, delimiter="\t" if name.endswith(".tsv") else ",")
        return self._parse_text(text)

    @staticmethod
    def _pdf_text(content: bytes) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise SeedParseError("password_protected_seed_pdf")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except SeedParseError:
            raise
        except Exception as exc:
            raise SeedParseError("malformed_seed_pdf") from exc
        if len(text) > MAX_SEED_TEXT_CHARACTERS:
            raise SeedParseError("seed_text_too_large")
        if len(text.strip()) < 20:
            raise SeedParseError("image_only_seed_requires_document_intelligence")
        return text

    @staticmethod
    def _parse_json(text: str, *, json_lines: bool) -> list[SeedCandidate]:
        try:
            raw = (
                [json.loads(line) for line in text.splitlines() if line.strip()]
                if json_lines
                else json.loads(text)
            )
            items = raw if isinstance(raw, list) else raw.get("scholarships", [])
            return [SeedCandidate.model_validate(item) for item in items]
        except (json.JSONDecodeError, AttributeError, ValidationError) as exc:
            raise SeedParseError("invalid_seed_json") from exc

    @staticmethod
    def _parse_csv(text: str, *, delimiter: str) -> list[SeedCandidate]:
        try:
            rows = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            return [
                SeedCandidate(
                    name=(row.get("name") or row.get("scholarship") or "").strip(),
                    provider=(row.get("provider") or "").strip() or None,
                    university=(row.get("university") or "").strip() or None,
                    country=(row.get("country") or "").strip() or None,
                    cycle=(row.get("cycle") or "").strip() or None,
                    intake_year=(int(row["intake_year"]) if row.get("intake_year") else None),
                    possible_official_url=(
                        row.get("possible_official_url") or row.get("official_url") or None
                    ),
                    keywords=_split_keywords(row.get("keywords") or ""),
                )
                for row in rows
            ]
        except (csv.Error, ValidationError, ValueError) as exc:
            raise SeedParseError("invalid_seed_csv") from exc

    @staticmethod
    def _parse_text(text: str) -> list[SeedCandidate]:
        candidates: list[SeedCandidate] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            line = BULLET_PATTERN.sub("", raw_line).strip()
            if len(line) < 3 or line.casefold().startswith(("scholarship name", "name |")):
                continue
            url_match = URL_PATTERN.search(line)
            url = url_match.group(0).rstrip(".,;") if url_match else None
            without_url = line.replace(url_match.group(0), "") if url_match else line
            parts = [
                part.strip(" -\N{EN DASH}\N{EM DASH}:;")
                for part in re.split(r"\s*[|\t]\s*", without_url)
            ]
            parts = [part for part in parts if part]
            name = parts[0] if parts else ""
            if "scholar" not in name.casefold() and len(parts) == 1 and not url:
                continue
            key = re.sub(r"\W+", "", name.casefold())
            if len(name) < 3 or key in seen:
                continue
            seen.add(key)
            try:
                candidates.append(
                    SeedCandidate(
                        name=name[:255],
                        provider=parts[1][:255] if len(parts) > 1 else None,
                        country=parts[2][:100] if len(parts) > 2 else None,
                        possible_official_url=url,
                        keywords=[word for word in re.findall(r"[A-Za-z]{4,}", name)[:8]],
                    )
                )
            except ValidationError:
                continue
        if not candidates:
            raise SeedParseError("no_seed_candidates_found")
        return candidates


class AzureDocumentIntelligenceParser:
    """Optional adapter boundary; disabled until a paid provider is explicitly configured."""

    def parse(self, document: LoadedSeed) -> list[SeedCandidate]:
        del document
        raise SeedParseError("document_intelligence_not_configured")


def _content_type_from_name(name: str) -> str:
    lowered = name.casefold()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith((".json", ".jsonl")):
        return "application/json"
    if lowered.endswith(".csv"):
        return "text/csv"
    if lowered.endswith(".tsv"):
        return "text/tab-separated-values"
    return "text/plain"


def _split_keywords(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,;]", value) if item.strip()][:20]
