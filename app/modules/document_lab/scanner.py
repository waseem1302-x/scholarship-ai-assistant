"""Malware scanner boundary. Unavailability is a fail-closed condition."""

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    code: str | None = None


class MalwareScanner(Protocol):
    def scan(self, content: bytes) -> ScanResult: ...


class ScannerUnavailable(RuntimeError):
    pass


class UnavailableScanner:
    def scan(self, content: bytes) -> ScanResult:
        del content
        raise ScannerUnavailable("No reviewed malware scanner is configured")


class SignatureTestScanner:
    """Deterministic test-only scanner; never enable it for production."""

    def scan(self, content: bytes) -> ScanResult:
        return ScanResult(clean=b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" not in content)


def get_scanner(settings: Settings) -> MalwareScanner:
    if settings.env == "test" and settings.document_lab_storage_provider == "test":
        return SignatureTestScanner()
    return UnavailableScanner()
