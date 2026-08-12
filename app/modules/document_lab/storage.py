"""Opaque encrypted local storage adapter used only for development and tests."""

import hashlib
import hmac
import os
import uuid
from contextlib import suppress
from pathlib import Path

from app.modules.document_lab.crypto import DocumentCipher


class LocalEncryptedDocumentStorage:
    """Private filesystem storage with opaque user-scoped keys.

    A production deployment must replace this adapter with a reviewed encrypted
    object-store provider. The API never exposes a storage key or filesystem
    path to the browser.
    """

    def __init__(self, root: str, cipher: DocumentCipher, key_material: str) -> None:
        self.root = Path(root).resolve()
        self.cipher = cipher
        self._key_material = key_material.encode("utf-8")

    def new_key(self, user_id: uuid.UUID, version_id: uuid.UUID) -> str:
        scope = hmac.new(
            self._key_material,
            str(user_id).encode("ascii"),
            hashlib.sha256,
        ).hexdigest()[:32]
        return f"private/{scope}/{version_id.hex}.bin"

    def write(self, key: str, content: bytes) -> None:
        path = self._path_for(key)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("xb") as handle:
            handle.write(self.cipher.encrypt_bytes(content))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        with suppress(OSError):
            path.chmod(0o600)

    def read(self, key: str) -> bytes:
        return self.cipher.decrypt_bytes(self._path_for(key).read_bytes())

    def delete(self, key: str) -> None:
        try:
            self._path_for(key).unlink()
        except FileNotFoundError:
            return

    def _path_for(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            raise ValueError("Document storage key escaped its private root")
        return candidate
