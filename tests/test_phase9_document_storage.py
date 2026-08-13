import io
import uuid

from app.core.config import Settings
from app.modules.document_lab.crypto import DocumentCipher
from app.modules.document_lab.storage import S3EncryptedDocumentStorage


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)
        self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))] = bytes(kwargs["Body"])

    def get_object(self, **kwargs: object) -> dict[str, io.BytesIO]:
        return {"Body": io.BytesIO(self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))])}

    def delete_object(self, **kwargs: object) -> None:
        self.objects.pop((str(kwargs["Bucket"]), str(kwargs["Key"])), None)


def test_s3_storage_uses_opaque_keys_client_encryption_and_kms() -> None:
    settings = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="s3-storage-test-secret-at-least-32-characters",
    )
    client = FakeS3Client()
    storage = S3EncryptedDocumentStorage(
        cipher=DocumentCipher(settings),
        key_material=settings.jwt_secret,
        bucket="private-documents",
        region="ap-southeast-1",
        kms_key_id="alias/private-documents",
        client=client,
    )
    key = storage.new_key(uuid.uuid4(), uuid.uuid4())

    storage.write(key, b"private resume text")

    assert key.startswith("private/")
    assert b"private resume text" not in client.objects[("private-documents", key)]
    assert client.put_calls[0]["ServerSideEncryption"] == "aws:kms"
    assert client.put_calls[0]["SSEKMSKeyId"] == "alias/private-documents"
    assert storage.read(key) == b"private resume text"
    storage.delete(key)
    assert ("private-documents", key) not in client.objects
