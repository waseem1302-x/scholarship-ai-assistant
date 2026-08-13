"""Opaque encrypted local storage adapter used only for development and tests."""

import hashlib
import hmac
import os
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.modules.document_lab.crypto import DocumentCipher


class DocumentStorage(Protocol):
    def new_key(self, user_id: uuid.UUID, version_id: uuid.UUID) -> str: ...

    def write(self, key: str, content: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


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


class S3EncryptedDocumentStorage:
    """Opaque, client-encrypted S3 objects with managed KMS at rest.

    The database only stores opaque scoped keys. Client-side authenticated
    encryption protects content before the object store sees it; S3 SSE-KMS
    supplies a second managed encryption boundary and auditable key control.
    """

    def __init__(
        self,
        *,
        cipher: DocumentCipher,
        key_material: str,
        bucket: str,
        region: str,
        kms_key_id: str,
        endpoint_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.cipher = cipher
        self.bucket = bucket
        self.kms_key_id = kms_key_id
        self._key_material = key_material.encode("utf-8")
        self._client = client or boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

    def new_key(self, user_id: uuid.UUID, version_id: uuid.UUID) -> str:
        scope = hmac.new(
            self._key_material, str(user_id).encode("ascii"), hashlib.sha256
        ).hexdigest()[:32]
        return f"private/{scope}/{version_id.hex}.bin"

    def write(self, key: str, content: bytes) -> None:
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=self._validated_key(key),
                Body=self.cipher.encrypt_bytes(content),
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=self.kms_key_id,
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("Private document storage is unavailable") from exc

    def read(self, key: str) -> bytes:
        try:
            result = self._client.get_object(Bucket=self.bucket, Key=self._validated_key(key))
            return self.cipher.decrypt_bytes(result["Body"].read())
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("Private document storage is unavailable") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._validated_key(key))
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("Private document storage is unavailable") from exc

    @staticmethod
    def _validated_key(key: str) -> str:
        if not key.startswith("private/") or ".." in key or "\\" in key:
            raise ValueError("Document storage key is invalid")
        return key
