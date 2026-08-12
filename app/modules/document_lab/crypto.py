"""Encryption boundary for Document Lab's sensitive persisted values."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.core.errors import AppError


class DocumentCipher:
    """Authenticated encryption for names, extracted text, feedback, and files.

    Development derives a local key from the already-required JWT secret so the
    repository never needs an additional plaintext key. Production startup
    rejects that mode and requires a deployment-secret key.
    """

    def __init__(self, settings: Settings) -> None:
        configured = settings.document_lab_encryption_key
        if configured is not None:
            key = configured.get_secret_value().encode("ascii")
        else:
            material = f"document-lab.v1:{settings.jwt_secret}".encode()
            key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
        try:
            self._fernet = Fernet(key)
        except (TypeError, ValueError) as exc:
            raise AppError(
                "document_encryption_configuration_invalid",
                "Document Lab encryption is not configured safely.",
                503,
            ) from exc

    def encrypt_text(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt_text(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise AppError(
                "document_data_unavailable",
                "The private document data is unavailable.",
                503,
            ) from exc

    def encrypt_bytes(self, value: bytes) -> bytes:
        return self._fernet.encrypt(value)

    def decrypt_bytes(self, value: bytes) -> bytes:
        try:
            return self._fernet.decrypt(value)
        except InvalidToken as exc:
            raise AppError(
                "document_data_unavailable",
                "The private document data is unavailable.",
                503,
            ) from exc
