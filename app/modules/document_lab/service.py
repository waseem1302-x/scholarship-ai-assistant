"""Owner-scoped, fail-closed document intake and asynchronous preparation."""

import hashlib
import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.auth.models import User, utc_now
from app.modules.document_lab.crypto import DocumentCipher
from app.modules.document_lab.extraction import extract_restricted
from app.modules.document_lab.models import (
    AnalysisStatus,
    DocumentAnalysisJob,
    DocumentAsset,
    DocumentExtraction,
    DocumentJobKind,
    DocumentKind,
    DocumentVersion,
    DocumentVersionStatus,
    ExtractionStatus,
    ScanStatus,
)
from app.modules.document_lab.scanner import MalwareScanner, ScannerUnavailable, get_scanner
from app.modules.document_lab.schemas import (
    DocumentAssetResponse,
    DocumentVersionResponse,
)
from app.modules.document_lab.storage import LocalEncryptedDocumentStorage
from app.modules.document_lab.validation import ValidatedDocument, validate_upload

Extractor = Callable[[bytes, str], str]


class DocumentLabService:
    """Keeps document bytes and text in a dedicated private security boundary."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        scanner: MalwareScanner | None = None,
        extractor: Extractor | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.cipher = DocumentCipher(settings)
        self.storage = LocalEncryptedDocumentStorage(
            settings.document_lab_storage_root,
            self.cipher,
            settings.jwt_secret,
        )
        self.scanner = scanner or get_scanner(settings)
        self.extractor = extractor or self._restricted_extract

    def create_asset(
        self,
        *,
        user: User,
        document_kind: DocumentKind,
        filename: str,
        declared_content_type: str,
        content: bytes,
    ) -> DocumentAssetResponse:
        self._require_enabled()
        self._purge_expired()
        self._enforce_daily_upload_limit(user.id)
        safe_name = self._safe_filename(filename)
        validated = self._validate(safe_name, declared_content_type, content)
        asset = DocumentAsset(
            user_id=user.id,
            document_kind=document_kind,
            display_name_ciphertext=self.cipher.encrypt_text(safe_name),
            retention_expires_at=utc_now()
            + timedelta(days=self.settings.document_lab_retention_days),
        )
        self.session.add(asset)
        self.session.flush()
        self._create_version(asset, user.id, 1, declared_content_type, content, validated)
        self.session.commit()
        return self._asset_response(asset)

    def add_version(
        self,
        *,
        asset_id: uuid.UUID,
        user: User,
        filename: str,
        declared_content_type: str,
        content: bytes,
    ) -> DocumentAssetResponse:
        self._require_enabled()
        self._purge_expired()
        self._enforce_daily_upload_limit(user.id)
        asset = self._owned_asset(asset_id, user.id)
        existing_name = self.cipher.decrypt_text(asset.display_name_ciphertext)
        if self._safe_filename(filename) != existing_name:
            raise AppError(
                "document_version_name_mismatch",
                "New versions must confirm the same private document name.",
                422,
            )
        validated = self._validate(existing_name, declared_content_type, content)
        next_number = (
            self.session.scalar(
                select(DocumentVersion.version_number)
                .where(DocumentVersion.asset_id == asset.id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
            or 0
        ) + 1
        self._create_version(asset, user.id, next_number, declared_content_type, content, validated)
        self.session.commit()
        return self._asset_response(asset)

    def list_assets(self, user_id: uuid.UUID) -> list[DocumentAssetResponse]:
        self._require_enabled()
        self._purge_expired()
        assets = self.session.scalars(
            select(DocumentAsset)
            .where(DocumentAsset.user_id == user_id, DocumentAsset.deleted_at.is_(None))
            .order_by(DocumentAsset.updated_at.desc())
        ).all()
        return [self._asset_response(asset) for asset in assets]

    def get_asset(self, asset_id: uuid.UUID, user_id: uuid.UUID) -> DocumentAssetResponse:
        self._require_enabled()
        self._purge_expired()
        return self._asset_response(self._owned_asset(asset_id, user_id))

    def download_version(self, version_id: uuid.UUID, user_id: uuid.UUID) -> tuple[bytes, str]:
        self._require_enabled()
        version = self._owned_version(version_id, user_id)
        if version.status is not DocumentVersionStatus.READY:
            raise AppError(
                "document_download_not_ready",
                "A document can be downloaded only after its safety checks complete.",
                409,
            )
        return self.storage.read(version.storage_key), version.detected_content_type

    def delete_asset(self, asset_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self._require_enabled()
        asset = self._owned_asset(asset_id, user_id)
        versions = self._versions_for_asset(asset.id)
        for version in versions:
            self.storage.delete(version.storage_key)
        self.session.delete(asset)
        self.session.commit()

    def process_next_job(self) -> bool:
        """Run exactly one queued preparation job for the worker CLI.

        It receives no user-selected content through command arguments and
        records only status codes on errors, never document-derived messages.
        """
        job = self.session.scalar(
            select(DocumentAnalysisJob)
            .where(DocumentAnalysisJob.status == AnalysisStatus.QUEUED)
            .order_by(DocumentAnalysisJob.created_at)
            .limit(1)
        )
        if job is None:
            return False
        job.status = AnalysisStatus.RUNNING
        job.started_at = utc_now()
        job.attempt_count += 1
        self.session.commit()
        if job.job_kind is DocumentJobKind.SCAN:
            self._process_scan(job)
        elif job.job_kind is DocumentJobKind.EXTRACT:
            self._process_extract(job)
        else:
            self._fail_job(job, "analysis_worker_not_ready")
        return True

    def _create_version(
        self,
        asset: DocumentAsset,
        user_id: uuid.UUID,
        number: int,
        declared_content_type: str,
        content: bytes,
        validated: ValidatedDocument,
    ) -> DocumentVersion:
        version_id = uuid.uuid4()
        key = self.storage.new_key(user_id, version_id)
        version = DocumentVersion(
            id=version_id,
            asset_id=asset.id,
            user_id=user_id,
            version_number=number,
            storage_key=key,
            content_sha256=hashlib.sha256(content).hexdigest(),
            declared_content_type=declared_content_type.split(";", maxsplit=1)[0].strip(),
            detected_content_type=validated.detected_content_type,
            size_bytes=len(content),
            page_count=validated.page_count,
        )
        self.storage.write(key, content)
        self.session.add(version)
        self.session.flush()
        self.session.add(
            DocumentAnalysisJob(
                version_id=version.id,
                user_id=user_id,
                job_kind=DocumentJobKind.SCAN,
                idempotency_key=f"scan:{version.id}",
            )
        )
        return version

    def _process_scan(self, job: DocumentAnalysisJob) -> None:
        version = self.session.get(DocumentVersion, job.version_id)
        if version is None:
            self._fail_job(job, "version_deleted")
            return
        version.status = DocumentVersionStatus.SCANNING
        try:
            result = self.scanner.scan(self.storage.read(version.storage_key))
        except ScannerUnavailable:
            version.scan_status = ScanStatus.UNAVAILABLE
            version.status = DocumentVersionStatus.FAILED
            self._fail_job(job, "malware_scanner_unavailable")
            return
        except Exception:
            version.scan_status = ScanStatus.FAILED
            version.status = DocumentVersionStatus.FAILED
            self._fail_job(job, "malware_scanner_failed")
            return
        if not result.clean:
            version.scan_status = ScanStatus.REJECTED
            version.status = DocumentVersionStatus.REJECTED
            version.rejection_code = result.code or "malware_detected"
            self._complete_job(job)
            return
        version.scan_status = ScanStatus.CLEAN
        version.status = DocumentVersionStatus.EXTRACTING
        self.session.add(DocumentExtraction(version_id=version.id, user_id=version.user_id))
        self.session.add(
            DocumentAnalysisJob(
                version_id=version.id,
                user_id=version.user_id,
                job_kind=DocumentJobKind.EXTRACT,
                idempotency_key=f"extract:{version.id}",
            )
        )
        self._complete_job(job)

    def _process_extract(self, job: DocumentAnalysisJob) -> None:
        version = self.session.get(DocumentVersion, job.version_id)
        extraction = self.session.scalar(
            select(DocumentExtraction).where(DocumentExtraction.version_id == job.version_id)
        )
        if version is None or extraction is None:
            self._fail_job(job, "version_deleted")
            return
        extraction.status = ExtractionStatus.RUNNING
        version.status = DocumentVersionStatus.EXTRACTING
        try:
            text = self.extractor(
                self.storage.read(version.storage_key), version.detected_content_type
            )
        except AppError as exc:
            extraction.status = ExtractionStatus.REJECTED
            extraction.failure_code = exc.code
            extraction.completed_at = utc_now()
            version.status = DocumentVersionStatus.FAILED
            version.rejection_code = exc.code
            self._fail_job(job, exc.code)
            return
        except Exception:
            extraction.status = ExtractionStatus.FAILED
            extraction.failure_code = "extraction_failed"
            extraction.completed_at = utc_now()
            version.status = DocumentVersionStatus.FAILED
            version.rejection_code = "extraction_failed"
            self._fail_job(job, "extraction_failed")
            return
        extraction.text_ciphertext = self.cipher.encrypt_text(text)
        extraction.extracted_character_count = len(text)
        extraction.status = ExtractionStatus.COMPLETED
        extraction.completed_at = utc_now()
        version.status = DocumentVersionStatus.READY
        self._complete_job(job)

    def _restricted_extract(self, content: bytes, content_type: str) -> str:
        return extract_restricted(
            content,
            content_type,
            max_characters=self.settings.document_lab_max_extracted_characters,
        )

    def _complete_job(self, job: DocumentAnalysisJob) -> None:
        job.status = AnalysisStatus.COMPLETED
        job.completed_at = utc_now()
        self.session.commit()

    def _fail_job(self, job: DocumentAnalysisJob, code: str) -> None:
        job.status = AnalysisStatus.FAILED
        job.failure_code = code
        job.completed_at = utc_now()
        self.session.commit()

    def _validate(
        self, filename: str, declared_content_type: str, content: bytes
    ) -> ValidatedDocument:
        return validate_upload(
            filename=filename,
            declared_content_type=declared_content_type,
            content=content,
            max_bytes=self.settings.document_lab_max_upload_bytes,
            max_pages=self.settings.document_lab_max_pages,
        )

    def _asset_response(self, asset: DocumentAsset) -> DocumentAssetResponse:
        return DocumentAssetResponse(
            id=asset.id,
            document_kind=asset.document_kind,
            display_name=self.cipher.decrypt_text(asset.display_name_ciphertext),
            retention_expires_at=asset.retention_expires_at,
            created_at=asset.created_at,
            versions=[self._version_response(item) for item in self._versions_for_asset(asset.id)],
        )

    def _version_response(self, version: DocumentVersion) -> DocumentVersionResponse:
        extraction = self.session.scalar(
            select(DocumentExtraction).where(DocumentExtraction.version_id == version.id)
        )
        return DocumentVersionResponse(
            id=version.id,
            asset_id=version.asset_id,
            version_number=version.version_number,
            declared_content_type=version.declared_content_type,
            detected_content_type=version.detected_content_type,
            size_bytes=version.size_bytes,
            page_count=version.page_count,
            status=version.status,
            scan_status=version.scan_status,
            extraction_status=extraction.status if extraction else None,
            rejection_code=version.rejection_code,
            created_at=version.created_at,
        )

    def _versions_for_asset(self, asset_id: uuid.UUID) -> list[DocumentVersion]:
        return self.session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.asset_id == asset_id)
            .order_by(DocumentVersion.version_number.desc())
        ).all()

    def _owned_asset(self, asset_id: uuid.UUID, user_id: uuid.UUID) -> DocumentAsset:
        asset = self.session.get(DocumentAsset, asset_id)
        if asset is None or asset.user_id != user_id or asset.deleted_at is not None:
            raise AppError("document_asset_not_found", "Document asset was not found.", 404)
        return asset

    def _owned_version(self, version_id: uuid.UUID, user_id: uuid.UUID) -> DocumentVersion:
        version = self.session.get(DocumentVersion, version_id)
        if version is None or version.user_id != user_id:
            raise AppError("document_version_not_found", "Document version was not found.", 404)
        return version

    def _enforce_daily_upload_limit(self, user_id: uuid.UUID) -> None:
        cutoff = utc_now() - timedelta(days=1)
        count = (
            self.session.scalar(
                select(func.count(DocumentVersion.id)).where(
                    DocumentVersion.user_id == user_id, DocumentVersion.created_at >= cutoff
                )
            )
            or 0
        )
        if count >= self.settings.document_lab_daily_user_limit:
            raise AppError("document_upload_quota_exceeded", "Document upload limit reached.", 429)

    def _purge_expired(self) -> None:
        expired = self.session.scalars(
            select(DocumentAsset).where(
                DocumentAsset.deleted_at.is_(None),
                DocumentAsset.retention_expires_at <= utc_now(),
            )
        ).all()
        for asset in expired:
            for version in self._versions_for_asset(asset.id):
                self.storage.delete(version.storage_key)
            self.session.delete(asset)
        if expired:
            self.session.commit()

    def _require_enabled(self) -> None:
        if not self.settings.document_lab_enabled:
            raise AppError(
                "document_lab_unavailable",
                "Document Lab is not enabled in this deployment.",
                503,
            )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
        if not name or name in {".", ".."}:
            raise AppError("invalid_filename", "The uploaded file cannot be accepted.", 422)
        return name
