"""Owner-scoped, fail-closed document intake and asynchronous preparation."""

import hashlib
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.auth.models import User, utc_now
from app.modules.document_lab.crypto import DocumentCipher
from app.modules.document_lab.extraction import extract_restricted
from app.modules.document_lab.models import (
    AnalysisProviderStatus,
    AnalysisStatus,
    ApplicationDocumentLink,
    DocumentAnalysis,
    DocumentAnalysisJob,
    DocumentAsset,
    DocumentConsent,
    DocumentDeletionStatus,
    DocumentExtraction,
    DocumentFeedbackItem,
    DocumentJobKind,
    DocumentKind,
    DocumentVersion,
    DocumentVersionStatus,
    ExtractionStatus,
    FeedbackCategory,
    ScanStatus,
)
from app.modules.document_lab.provider import (
    DocumentProvider,
    DocumentProviderError,
    DocumentProviderTimeout,
    ProviderAnalysisOutput,
    ProviderFeedbackItem,
    get_provider,
)
from app.modules.document_lab.scanner import (
    MalwareScanner,
    ScannerUnavailable,
    get_scanner,
)
from app.modules.document_lab.schemas import (
    ApplicationDocumentLinkResponse,
    DocumentAnalysisResponse,
    DocumentAssetResponse,
    DocumentExportResponse,
    DocumentFeedbackResponse,
    DocumentVersionResponse,
)
from app.modules.document_lab.storage import (
    DocumentStorage,
    LocalEncryptedDocumentStorage,
    S3EncryptedDocumentStorage,
)
from app.modules.document_lab.validation import (
    ValidatedDocument,
    validate_upload,
)
from app.modules.operations.models import OperationalJobHealth

Extractor = Callable[[bytes, str], str]


def document_intake_readiness(session: Session, settings: Settings) -> tuple[bool, bool, bool]:
    """Return scanner, worker, and effective intake readiness from one policy source."""
    scanner_ready = settings.document_lab_scanner_provider == "clamav" or (
        settings.env != "production" and settings.document_lab_scanner_provider == "test"
    )
    health = session.get(OperationalJobHealth, "document_jobs")
    worker_ready = bool(
        health
        and health.last_completed_at
        and (
            datetime.now(UTC)
            - (
                health.last_completed_at.replace(tzinfo=UTC)
                if health.last_completed_at.tzinfo is None
                else health.last_completed_at.astimezone(UTC)
            )
        )
        <= timedelta(minutes=settings.operational_job_stale_minutes)
        and health.last_error_code is None
    )
    accepting_uploads = settings.document_lab_enabled and (
        settings.env != "production" or (scanner_ready and worker_ready)
    )
    return scanner_ready, worker_ready, accepting_uploads


class DocumentLabService:
    """Keeps document bytes and text in a dedicated private security boundary."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        scanner: MalwareScanner | None = None,
        extractor: Extractor | None = None,
        provider: DocumentProvider | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.cipher = DocumentCipher(settings)
        self.storage: DocumentStorage = self._storage_for(settings)
        self.scanner = scanner or get_scanner(settings)
        self.extractor = extractor or self._restricted_extract
        self.provider = provider or get_provider(settings)

    def _storage_for(self, settings: Settings) -> DocumentStorage:
        if settings.document_lab_storage_provider == "s3-compatible":
            assert settings.document_lab_s3_bucket
            assert settings.document_lab_s3_region
            assert settings.document_lab_s3_kms_key_id
            return S3EncryptedDocumentStorage(
                cipher=self.cipher,
                key_material=settings.jwt_secret,
                bucket=settings.document_lab_s3_bucket,
                region=settings.document_lab_s3_region,
                kms_key_id=settings.document_lab_s3_kms_key_id,
                endpoint_url=settings.document_lab_s3_endpoint_url,
            )
        return LocalEncryptedDocumentStorage(
            settings.document_lab_storage_root,
            self.cipher,
            settings.jwt_secret,
        )

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
        self._require_intake_ready()
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
        version = self._create_version(asset, user.id, 1, declared_content_type, content, validated)
        self._commit_with_storage_compensation([version.storage_key])
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
        self._require_intake_ready()
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
        asset.retention_expires_at = utc_now() + timedelta(
            days=self.settings.document_lab_retention_days
        )
        version = self._create_version(
            asset,
            user.id,
            next_number,
            declared_content_type,
            content,
            validated,
        )
        self._commit_with_storage_compensation([version.storage_key])
        return self._asset_response(asset)

    def list_assets(self, user_id: uuid.UUID) -> list[DocumentAssetResponse]:
        # Listing is used by export/deletion rights and is safe while intake is
        # disabled: it reads only the requesting owner's already-held records.
        self._purge_expired()
        assets = self.session.scalars(
            select(DocumentAsset)
            .where(
                DocumentAsset.user_id == user_id,
                DocumentAsset.deleted_at.is_(None),
            )
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
        self._delete_asset_private_data(asset)

    def retry_preparation(
        self, version_id: uuid.UUID, user_id: uuid.UUID
    ) -> DocumentVersionResponse:
        """Explicitly retry a failed scanner/extractor job without duplicating content."""
        self._require_enabled()
        version = self._owned_version(version_id, user_id)
        if version.status is not DocumentVersionStatus.FAILED:
            raise AppError(
                "document_retry_not_available",
                "Only a failed private document can be retried.",
                409,
            )
        version.status = DocumentVersionStatus.QUARANTINED
        version.scan_status = ScanStatus.PENDING
        version.rejection_code = None
        extraction = self.session.scalar(
            select(DocumentExtraction).where(DocumentExtraction.version_id == version.id)
        )
        if extraction:
            extraction.status = ExtractionStatus.PENDING
            extraction.failure_code = None
            extraction.completed_at = None
        self.session.add(
            DocumentAnalysisJob(
                version_id=version.id,
                user_id=user_id,
                job_kind=DocumentJobKind.SCAN,
                idempotency_key=f"scan-retry:{version.id}:{uuid.uuid4().hex}",
            )
        )
        self.session.commit()
        return self._version_response(version)

    def request_analysis(
        self,
        *,
        version_id: uuid.UUID,
        user: User,
        analysis_type: DocumentKind,
        consent: bool,
        notice_version: str,
    ) -> DocumentAnalysisResponse:
        self._require_enabled()
        analysis_type = DocumentKind(analysis_type)
        self._enforce_analysis_quota(user.id)
        version = self._owned_version(version_id, user.id)
        if version.status is not DocumentVersionStatus.READY:
            raise AppError(
                "document_not_ready_for_analysis",
                "Document extraction is not ready.",
                409,
            )
        asset = self._owned_asset(version.asset_id, user.id)
        if asset.document_kind is not analysis_type:
            raise AppError(
                "document_analysis_type_mismatch",
                "Analysis type must match the document.",
                422,
            )
        if not consent or notice_version != self.settings.document_lab_notice_version:
            raise AppError(
                "document_analysis_consent_required",
                "Review and accept the current document data-use notice before analysis.",
                403,
            )
        from app.modules.document_lab.models import DocumentConsent

        consent_record = DocumentConsent(
            version_id=version.id,
            user_id=user.id,
            analysis_type=analysis_type,
            notice_version=notice_version,
            provider_config_version=self.settings.document_lab_provider_config_version,
        )
        self.session.add(consent_record)
        self.session.flush()
        analysis = DocumentAnalysis(
            version_id=version.id,
            user_id=user.id,
            consent_id=consent_record.id,
            analysis_type=analysis_type,
            provider=self.provider.name,
            model_version=self.provider.model_version,
            provider_config_version=self.settings.document_lab_provider_config_version,
            rubric_version=self.settings.document_lab_rubric_version,
        )
        self.session.add(analysis)
        self.session.flush()
        self.session.add(
            DocumentAnalysisJob(
                version_id=version.id,
                analysis_id=analysis.id,
                user_id=user.id,
                job_kind=DocumentJobKind.ANALYSE,
                idempotency_key=f"analysis:{analysis.id}",
            )
        )
        self.session.commit()
        return self._analysis_response(analysis)

    def get_analysis(self, analysis_id: uuid.UUID, user_id: uuid.UUID) -> DocumentAnalysisResponse:
        self._require_enabled()
        analysis = self.session.get(DocumentAnalysis, analysis_id)
        if analysis is None or analysis.user_id != user_id:
            raise AppError(
                "document_analysis_not_found",
                "Document analysis was not found.",
                404,
            )
        return self._analysis_response(analysis)

    def list_version_analyses(
        self, version_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[DocumentAnalysisResponse]:
        self._require_enabled()
        self._owned_version(version_id, user_id)
        analyses = self.session.scalars(
            select(DocumentAnalysis)
            .where(
                DocumentAnalysis.version_id == version_id,
                DocumentAnalysis.user_id == user_id,
            )
            .order_by(DocumentAnalysis.created_at.desc())
        ).all()
        return [self._analysis_response(item) for item in analyses]

    def export_data(self, user_id: uuid.UUID) -> DocumentExportResponse:
        # Privacy rights remain available while the feature is killed/switched
        # off; this path performs no upload, analysis, or provider work.
        assets = self.list_assets(user_id)
        analyses = self.session.scalars(
            select(DocumentAnalysis)
            .where(DocumentAnalysis.user_id == user_id)
            .order_by(DocumentAnalysis.created_at)
        ).all()
        return DocumentExportResponse(
            exported_at=utc_now(),
            assets=assets,
            analyses=[self._analysis_response(item) for item in analyses],
        )

    def delete_all_data(self, user_id: uuid.UUID) -> None:
        # A kill switch must not strand private storage objects or prevent a
        # student from exercising deletion rights.
        for asset in self.session.scalars(
            select(DocumentAsset).where(DocumentAsset.user_id == user_id)
        ).all():
            self._delete_asset_private_data(asset)

    def link_application_document(
        self,
        *,
        application_document_id: uuid.UUID,
        version_id: uuid.UUID,
        user_id: uuid.UUID,
        confirmed: bool,
    ) -> ApplicationDocumentLinkResponse:
        if not confirmed:
            raise AppError(
                "document_link_confirmation_required",
                "Confirm before linking a document.",
                422,
            )
        from app.modules.applications.models import (
            Application,
            ApplicationDocument,
        )

        application_document = self.session.scalar(
            select(ApplicationDocument)
            .join(
                Application,
                Application.id == ApplicationDocument.application_id,
            )
            .where(
                ApplicationDocument.id == application_document_id,
                Application.user_id == user_id,
            )
        )
        if application_document is None:
            raise AppError(
                "application_document_not_found",
                "Application document was not found.",
                404,
            )
        self._owned_version(version_id, user_id)
        link = self.session.scalar(
            select(ApplicationDocumentLink).where(
                ApplicationDocumentLink.application_document_id == application_document_id,
                ApplicationDocumentLink.version_id == version_id,
            )
        )
        if link is None:
            link = ApplicationDocumentLink(
                application_document_id=application_document_id,
                version_id=version_id,
                user_id=user_id,
            )
            self.session.add(link)
            self.session.commit()
        return ApplicationDocumentLinkResponse(
            id=link.id,
            application_document_id=link.application_document_id,
            version_id=link.version_id,
            confirmed_at=link.confirmed_at,
        )

    def process_next_job(self) -> bool:
        """Run exactly one queued preparation job for the worker CLI.

        It receives no user-selected content through command arguments and
        records only status codes on errors, never document-derived messages.
        """
        job = self._claim_next_job()
        if job is None:
            return False
        if job.job_kind is DocumentJobKind.SCAN:
            self._process_scan(job)
        elif job.job_kind is DocumentJobKind.EXTRACT:
            self._process_extract(job)
        elif job.job_kind is DocumentJobKind.ANALYSE:
            self._process_analysis(job)
        else:
            self._fail_job(job, "analysis_worker_not_ready")
        return True

    def _claim_next_job(self) -> DocumentAnalysisJob | None:
        queued_job_id = (
            select(DocumentAnalysisJob.id)
            .where(DocumentAnalysisJob.status == AnalysisStatus.QUEUED)
            .order_by(DocumentAnalysisJob.created_at, DocumentAnalysisJob.id)
            .limit(1)
            .scalar_subquery()
        )
        claimed_id = self.session.scalar(
            update(DocumentAnalysisJob)
            .where(
                DocumentAnalysisJob.id == queued_job_id,
                DocumentAnalysisJob.status == AnalysisStatus.QUEUED,
            )
            .values(
                status=AnalysisStatus.RUNNING,
                started_at=utc_now(),
                attempt_count=DocumentAnalysisJob.attempt_count + 1,
            )
            .returning(DocumentAnalysisJob.id)
            .execution_options(synchronize_session=False)
        )
        if claimed_id is None:
            self.session.rollback()
            return None
        self.session.commit()
        return self.session.get(DocumentAnalysisJob, claimed_id)

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
            encryption_key_version=self.settings.document_lab_encryption_key_version,
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
        extraction = self.session.scalar(
            select(DocumentExtraction).where(DocumentExtraction.version_id == version.id)
        )
        if extraction is None:
            self.session.add(DocumentExtraction(version_id=version.id, user_id=version.user_id))
        else:
            extraction.status = ExtractionStatus.PENDING
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
                self.storage.read(version.storage_key),
                version.detected_content_type,
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

    def _process_analysis(self, job: DocumentAnalysisJob) -> None:
        analysis = self.session.get(DocumentAnalysis, job.analysis_id)
        extraction = self.session.scalar(
            select(DocumentExtraction).where(DocumentExtraction.version_id == job.version_id)
        )
        if (
            analysis is None
            or extraction is None
            or extraction.status is not ExtractionStatus.COMPLETED
        ):
            self._fail_job(job, "document_not_ready_for_analysis")
            return
        analysis.status = AnalysisStatus.RUNNING
        try:
            extracted_text = self.cipher.decrypt_text(extraction.text_ciphertext or "")
            output = ProviderAnalysisOutput.model_validate(
                self._analyse_with_timeout(extracted_text, analysis.analysis_type)
            )
            self._validate_provider_output(output, extracted_text)
        except DocumentProviderError as exc:
            analysis.status = AnalysisStatus.FAILED
            analysis.provider_status = AnalysisProviderStatus(exc.status)
            analysis.failure_code = f"provider_{exc.status}"
            analysis.completed_at = utc_now()
            self._fail_job(job, analysis.failure_code)
            return
        except (AppError, ValueError):
            analysis.status = AnalysisStatus.ABSTAINED
            analysis.provider_status = AnalysisProviderStatus.INVALID_RESPONSE
            analysis.abstained_reason = "invalid_provider_response"
            analysis.completed_at = utc_now()
            self._complete_job(job)
            return
        analysis.summary_ciphertext = self.cipher.encrypt_text(output.summary)
        analysis.confidence = output.confidence
        if output.abstained_reason:
            analysis.status = AnalysisStatus.ABSTAINED
            analysis.provider_status = AnalysisProviderStatus.ABSTAINED
            analysis.abstained_reason = output.abstained_reason
        else:
            analysis.status = AnalysisStatus.COMPLETED
            analysis.provider_status = AnalysisProviderStatus.COMPLETED
        for position, item in enumerate(self._provider_items(output), start=1):
            self.session.add(
                DocumentFeedbackItem(
                    analysis_id=analysis.id,
                    category=item.category,
                    text_ciphertext=self.cipher.encrypt_text(item.text),
                    excerpt_ciphertext=self.cipher.encrypt_text(item.excerpt)
                    if item.excerpt
                    else None,
                    rubric_category=item.rubric_category or item.category.value,
                    confidence=item.confidence,
                    is_general_suggestion=item.is_general_suggestion,
                    position=position,
                )
            )
        analysis.completed_at = utc_now()
        self._complete_job(job)

    @staticmethod
    def _provider_items(
        output: ProviderAnalysisOutput,
    ) -> list[ProviderFeedbackItem]:
        categories = (
            (FeedbackCategory.STRENGTH, output.strengths),
            (FeedbackCategory.SUGGESTION, output.suggestions),
            (FeedbackCategory.QUESTION, output.questions_to_consider),
            (FeedbackCategory.WARNING, output.warnings),
        )
        items: list[ProviderFeedbackItem] = []
        for category, values in categories:
            for value in values:
                items.append(
                    value.model_copy(
                        update={
                            "category": category,
                            "rubric_category": value.rubric_category or category.value,
                        }
                    )
                )
        return items

    @staticmethod
    def _validate_provider_output(output: ProviderAnalysisOutput, text: str) -> None:
        prohibited = (
            "you are eligible",
            "will be accepted",
            "guarantee",
            "plagiarism",
        )
        all_text = " ".join(
            [output.summary] + [item.text for item in DocumentLabService._provider_items(output)]
        ).casefold()
        if any(term in all_text for term in prohibited):
            raise AppError(
                "invalid_provider_response",
                "Provider output was not safe.",
                422,
            )
        for item in DocumentLabService._provider_items(output):
            if not item.rubric_category or item.confidence not in {"low", "medium", "high"}:
                raise AppError(
                    "invalid_provider_response",
                    "Provider output was not structured.",
                    422,
                )
            if item.is_general_suggestion:
                if item.excerpt:
                    raise AppError(
                        "invalid_provider_response",
                        "Provider output was not safe.",
                        422,
                    )
            elif not item.excerpt or item.excerpt not in text:
                raise AppError(
                    "invalid_provider_response",
                    "Provider output was not grounded.",
                    422,
                )

    def _analysis_response(self, analysis: DocumentAnalysis) -> DocumentAnalysisResponse:
        items = self.session.scalars(
            select(DocumentFeedbackItem)
            .where(DocumentFeedbackItem.analysis_id == analysis.id)
            .order_by(DocumentFeedbackItem.position)
        ).all()
        feedback = [
            DocumentFeedbackResponse(
                id=item.id,
                category=item.category,
                text=self.cipher.decrypt_text(item.text_ciphertext),
                excerpt=self.cipher.decrypt_text(item.excerpt_ciphertext)
                if item.excerpt_ciphertext
                else None,
                rubric_category=item.rubric_category,
                confidence=item.confidence,
                is_general_suggestion=item.is_general_suggestion,
                position=item.position,
            )
            for item in items
        ]
        by_category = {
            category: [item for item in feedback if item.category is category]
            for category in FeedbackCategory
        }
        return DocumentAnalysisResponse(
            id=analysis.id,
            version_id=analysis.version_id,
            analysis_type=analysis.analysis_type,
            status=analysis.status,
            provider_status=analysis.provider_status,
            rubric_version=analysis.rubric_version,
            provider=analysis.provider,
            model_version=analysis.model_version,
            summary=self.cipher.decrypt_text(analysis.summary_ciphertext)
            if analysis.summary_ciphertext
            else None,
            confidence=analysis.confidence,
            abstained_reason=analysis.abstained_reason,
            created_at=analysis.created_at,
            completed_at=analysis.completed_at,
            feedback=feedback,
            strengths=by_category[FeedbackCategory.STRENGTH],
            suggestions=by_category[FeedbackCategory.SUGGESTION],
            questions_to_consider=by_category[FeedbackCategory.QUESTION],
            warnings=by_category[FeedbackCategory.WARNING],
            quoted_evidence=[item.excerpt for item in feedback if item.excerpt],
        )

    def _delete_analysis_records(self, version_ids: list[uuid.UUID]) -> None:
        if not version_ids:
            return
        analysis_rows = self.session.execute(
            select(DocumentAnalysis.id, DocumentAnalysis.consent_id).where(
                DocumentAnalysis.version_id.in_(version_ids)
            )
        ).all()
        analysis_ids = [row.id for row in analysis_rows]
        consent_ids = [row.consent_id for row in analysis_rows]
        self.session.execute(
            delete(DocumentAnalysisJob).where(DocumentAnalysisJob.version_id.in_(version_ids))
        )
        if analysis_ids:
            self.session.execute(
                delete(DocumentFeedbackItem).where(
                    DocumentFeedbackItem.analysis_id.in_(analysis_ids)
                )
            )
            self.session.execute(
                delete(DocumentAnalysis).where(DocumentAnalysis.id.in_(analysis_ids))
            )
        if consent_ids:
            self.session.execute(delete(DocumentConsent).where(DocumentConsent.id.in_(consent_ids)))
        self.session.execute(
            delete(DocumentConsent).where(DocumentConsent.version_id.in_(version_ids))
        )

    def _restricted_extract(self, content: bytes, content_type: str) -> str:
        return extract_restricted(
            content,
            content_type,
            max_characters=self.settings.document_lab_max_extracted_characters,
        )

    def _analyse_with_timeout(
        self, text: str, analysis_type: DocumentKind
    ) -> ProviderAnalysisOutput:
        deadline_analyser = getattr(self.provider, "analyse_with_deadline", None)
        if callable(deadline_analyser):
            return deadline_analyser(
                text,
                analysis_type,
                timeout_seconds=self.settings.document_lab_provider_timeout_seconds,
            )
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self.provider.analyse, text, analysis_type)
            try:
                return future.result(timeout=self.settings.document_lab_provider_timeout_seconds)
            except TimeoutError as exc:
                future.cancel()
                raise DocumentProviderTimeout("Document provider timed out") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

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
            encryption_key_version=version.encryption_key_version,
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
            raise AppError(
                "document_asset_not_found",
                "Document asset was not found.",
                404,
            )
        return asset

    def _owned_version(self, version_id: uuid.UUID, user_id: uuid.UUID) -> DocumentVersion:
        version = self.session.get(DocumentVersion, version_id)
        if version is None or version.user_id != user_id:
            raise AppError(
                "document_version_not_found",
                "Document version was not found.",
                404,
            )
        return version

    def _enforce_daily_upload_limit(self, user_id: uuid.UUID) -> None:
        cutoff = utc_now() - timedelta(days=1)
        count = (
            self.session.scalar(
                select(func.count(DocumentVersion.id)).where(
                    DocumentVersion.user_id == user_id,
                    DocumentVersion.created_at >= cutoff,
                )
            )
            or 0
        )
        if count >= self.settings.document_lab_daily_user_limit:
            raise AppError(
                "document_upload_quota_exceeded",
                "Document upload limit reached.",
                429,
            )

    def _enforce_analysis_quota(self, user_id: uuid.UUID) -> None:
        cutoff = utc_now() - timedelta(days=1)
        count = (
            self.session.scalar(
                select(func.count(DocumentAnalysis.id)).where(
                    DocumentAnalysis.user_id == user_id,
                    DocumentAnalysis.created_at >= cutoff,
                )
            )
            or 0
        )
        if count >= self.settings.document_lab_daily_analysis_limit:
            raise AppError(
                "document_analysis_quota_exceeded",
                "Document analysis limit reached.",
                429,
            )

    def purge_expired(self) -> int:
        """Delete expired private objects/records even when intake is disabled."""
        return self._purge_expired()

    def _purge_expired(self) -> int:
        processed = self._purge_expired_analyses()
        expired = self.session.scalars(
            select(DocumentAsset).where(
                DocumentAsset.deleted_at.is_(None),
                DocumentAsset.retention_expires_at <= utc_now(),
            )
        ).all()
        for asset in expired:
            self._delete_asset_private_data(asset)
        return processed + len(expired)

    def _purge_expired_analyses(self) -> int:
        cutoff = utc_now() - timedelta(days=self.settings.document_lab_analysis_retention_days)
        rows = self.session.execute(
            select(DocumentAnalysis.id, DocumentAnalysis.consent_id).where(
                func.coalesce(DocumentAnalysis.completed_at, DocumentAnalysis.created_at) <= cutoff
            )
        ).all()
        if not rows:
            return 0
        analysis_ids = [row.id for row in rows]
        consent_ids = [row.consent_id for row in rows]
        self.session.execute(
            delete(DocumentFeedbackItem).where(DocumentFeedbackItem.analysis_id.in_(analysis_ids))
        )
        self.session.execute(
            delete(DocumentAnalysisJob).where(DocumentAnalysisJob.analysis_id.in_(analysis_ids))
        )
        self.session.execute(delete(DocumentAnalysis).where(DocumentAnalysis.id.in_(analysis_ids)))
        self.session.execute(delete(DocumentConsent).where(DocumentConsent.id.in_(consent_ids)))
        self.session.commit()
        return len(analysis_ids)

    def _delete_asset_private_data(self, asset: DocumentAsset) -> None:
        versions = self._versions_for_asset(asset.id)
        version_ids = [version.id for version in versions]
        now = utc_now()
        asset.deleted_at = asset.deleted_at or now
        asset.deletion_requested_at = asset.deletion_requested_at or now
        asset.deletion_status = DocumentDeletionStatus.PENDING_DELETE.value
        self.session.commit()
        for version in versions:
            self.storage.delete(version.storage_key)
        for version in versions:
            version.status = DocumentVersionStatus.DELETED
        asset.deletion_status = DocumentDeletionStatus.OBJECT_DELETED.value
        self.session.commit()
        self._delete_analysis_records(version_ids)
        self.session.delete(asset)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _commit_with_storage_compensation(self, storage_keys: list[str]) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            self._delete_storage_keys(storage_keys)
            raise

    def _delete_storage_keys(self, storage_keys: list[str]) -> None:
        for key in storage_keys:
            with suppress(Exception):
                self.storage.delete(key)

    def _require_enabled(self) -> None:
        if not self.settings.document_lab_enabled:
            raise AppError(
                "document_lab_unavailable",
                "Document Lab is not enabled in this deployment.",
                503,
            )

    def _require_intake_ready(self) -> None:
        if not document_intake_readiness(self.session, self.settings)[2]:
            raise AppError(
                "document_lab_intake_not_ready",
                "Document intake is paused until the scanner and preparation worker are healthy.",
                503,
            )

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
        if not name or name in {".", ".."}:
            raise AppError(
                "invalid_filename",
                "The uploaded file cannot be accepted.",
                422,
            )
        return name
