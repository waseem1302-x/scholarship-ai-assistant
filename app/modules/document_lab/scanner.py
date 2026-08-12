"""Malware scanner boundary. Unavailability is a fail-closed condition."""

import socket
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


class ClamAvScanner:
    """Minimal clamd INSTREAM adapter with no document logging.

    A scan error deliberately raises ScannerUnavailable so the job fails closed.
    The adapter talks only to the configured internal scanner endpoint; it never
    exposes document bytes to the browser or application logs.
    """

    def __init__(self, host: str, port: int, timeout_seconds: int) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def scan(self, content: bytes) -> ScanResult:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout_seconds
            ) as connection:
                connection.sendall(b"zINSTREAM\x00")
                for offset in range(0, len(content), 32_768):
                    chunk = content[offset : offset + 32_768]
                    connection.sendall(len(chunk).to_bytes(4, "big") + chunk)
                connection.sendall((0).to_bytes(4, "big"))
                response = connection.recv(4096).decode("utf-8", errors="replace")
        except OSError as exc:
            raise ScannerUnavailable("ClamAV is unavailable") from exc
        if "OK" in response:
            return ScanResult(clean=True)
        if "FOUND" in response:
            return ScanResult(clean=False, code="malware_detected")
        raise ScannerUnavailable("ClamAV returned an invalid response")


def get_scanner(settings: Settings) -> MalwareScanner:
    if settings.env == "test" and settings.document_lab_storage_provider == "test":
        return SignatureTestScanner()
    if settings.document_lab_scanner_provider == "clamav":
        return ClamAvScanner(
            settings.document_lab_scanner_host,
            settings.document_lab_scanner_port,
            settings.document_lab_scanner_timeout_seconds,
        )
    return UnavailableScanner()
