import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError
from app.modules.auth.models import User
from app.modules.opportunities.models import (
    Opportunity,
    OpportunityStatus,
    Source,
    SourceType,
    VerificationRecord,
    VerificationStatus,
)
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.schemas import (
    AdminOpportunityResponse,
    ImportRowStatus,
    OpportunityCreate,
    OpportunityDetailResponse,
    OpportunityImportRequest,
    OpportunityImportResponse,
    OpportunityImportRowResult,
    OpportunitySummaryResponse,
    SourceResponse,
    VerificationUpdate,
)


class OpportunityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OpportunityRepository(session)

    def create_opportunity(
        self, payload: OpportunityCreate, *, created_by: User
    ) -> AdminOpportunityResponse:
        provider = self.repository.get_or_create_provider(
            payload.provider_name,
            str(payload.provider_website_url) if payload.provider_website_url else None,
        )
        university = self.repository.get_or_create_university(
            payload.university_name,
            payload.country,
            str(payload.university_website_url) if payload.university_website_url else None,
        )

        opportunity = Opportunity(
            provider_id=provider.id,
            university_id=university.id if university else None,
            name=payload.name,
            country=payload.country,
            degree_level=payload.degree_level,
            field_eligibility=payload.field_eligibility,
            nationality_eligibility=payload.nationality_eligibility,
            application_opening_date=payload.application_opening_date,
            application_deadline=payload.application_deadline,
            intake_year=payload.intake_year,
            funding_type=payload.funding_type,
            tuition_coverage=payload.tuition_coverage,
            monthly_stipend_amount=payload.monthly_stipend_amount,
            monthly_stipend_currency=payload.monthly_stipend_currency,
            accommodation_coverage=payload.accommodation_coverage,
            travel_allowance=payload.travel_allowance,
            health_insurance=payload.health_insurance,
            application_fee_info=payload.application_fee_info,
            english_language_requirement=payload.english_language_requirement,
            standardized_test_requirement=payload.standardized_test_requirement,
            minimum_academic_requirement=payload.minimum_academic_requirement,
            required_documents=payload.required_documents,
            application_method=payload.application_method,
            application_url=str(payload.application_url) if payload.application_url else None,
            status=payload.status,
            data_confidence=payload.data_confidence,
            notes=payload.notes,
            eligibility_warnings=payload.eligibility_warnings,
            created_by_user_id=created_by.id,
        )
        opportunity.sources.append(
            Source(
                url=str(payload.source.url),
                source_type=payload.source.source_type,
                title=payload.source.title.strip(),
                publication_date=payload.source.publication_date,
                content_hash=payload.source.content_hash,
                relevant_excerpt=payload.source.relevant_excerpt.strip(),
                verification_status=payload.source.verification_status,
                verified_by_user_id=created_by.id
                if payload.source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
                else None,
                last_verified_at=datetime.now(UTC)
                if payload.source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
                else None,
            )
        )
        self.repository.add_opportunity(opportunity)

        try:
            self.session.commit()
            self.session.refresh(opportunity)
            return self.to_admin_response(opportunity)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "duplicate_opportunity",
                "An opportunity with the same provider, name, country, and intake already exists",
            ) from exc

    def import_opportunities(
        self, payload: OpportunityImportRequest, *, created_by: User
    ) -> OpportunityImportResponse:
        results: list[OpportunityImportRowResult] = []
        seen_keys: set[tuple[str, str, str, int | None]] = set()

        for row_number, raw_row in enumerate(payload.rows, start=1):
            prepared_row, preparation_warnings = self._prepare_import_row(raw_row)
            try:
                opportunity_payload = OpportunityCreate.model_validate(prepared_row)
            except ValidationError as exc:
                results.append(
                    OpportunityImportRowResult(
                        row_number=row_number,
                        status=ImportRowStatus.FAILED_VALIDATION,
                        errors=self._validation_messages(exc),
                        warnings=preparation_warnings,
                    )
                )
                continue

            warnings = preparation_warnings + self._data_quality_warnings(opportunity_payload)
            duplicate_key = self._duplicate_key(opportunity_payload)
            if duplicate_key in seen_keys:
                results.append(
                    OpportunityImportRowResult(
                        row_number=row_number,
                        status=ImportRowStatus.SKIPPED_DUPLICATE,
                        errors=["Duplicate row in the same import batch"],
                        warnings=warnings,
                    )
                )
                continue
            seen_keys.add(duplicate_key)

            duplicate = self.repository.find_duplicate_opportunity(
                provider_name=opportunity_payload.provider_name,
                name=opportunity_payload.name,
                country=opportunity_payload.country,
                intake_year=opportunity_payload.intake_year,
            )
            if duplicate is not None:
                results.append(
                    OpportunityImportRowResult(
                        row_number=row_number,
                        status=ImportRowStatus.SKIPPED_DUPLICATE,
                        opportunity_id=duplicate.id,
                        errors=[
                            "Opportunity already exists for provider, name, country, and intake"
                        ],
                        warnings=warnings,
                    )
                )
                continue

            if payload.dry_run:
                results.append(
                    OpportunityImportRowResult(
                        row_number=row_number,
                        status=ImportRowStatus.DRY_RUN_READY,
                        warnings=warnings,
                    )
                )
                continue

            try:
                created = self.create_opportunity(opportunity_payload, created_by=created_by)
            except AppError as exc:
                results.append(
                    OpportunityImportRowResult(
                        row_number=row_number,
                        status=ImportRowStatus.FAILED_VALIDATION,
                        errors=[exc.message],
                        warnings=warnings,
                    )
                )
                continue

            results.append(
                OpportunityImportRowResult(
                    row_number=row_number,
                    status=ImportRowStatus.IMPORTED,
                    opportunity_id=created.id,
                    warnings=warnings,
                )
            )

        return OpportunityImportResponse(
            source_format=payload.source_format,
            dry_run=payload.dry_run,
            total_rows=len(payload.rows),
            imported_count=sum(
                1 for result in results if result.status is ImportRowStatus.IMPORTED
            ),
            duplicate_count=sum(
                1 for result in results if result.status is ImportRowStatus.SKIPPED_DUPLICATE
            ),
            failed_count=sum(
                1 for result in results if result.status is ImportRowStatus.FAILED_VALIDATION
            ),
            results=results,
        )

    def verify_source(
        self, opportunity_id: uuid.UUID, payload: VerificationUpdate, *, checked_by: User
    ) -> AdminOpportunityResponse:
        opportunity = self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise AppError("opportunity_not_found", "Opportunity was not found", 404)

        source = self._select_source(opportunity, payload.source_id)
        source.verification_status = payload.verification_status
        source.verified_by_user_id = checked_by.id
        if payload.verification_status is VerificationStatus.OFFICIALLY_VERIFIED:
            source.last_verified_at = datetime.now(UTC)
            opportunity.status = OpportunityStatus.ACTIVE
        elif payload.verification_status is VerificationStatus.EXPIRED:
            opportunity.status = OpportunityStatus.EXPIRED

        self.session.add(
            VerificationRecord(
                opportunity_id=opportunity.id,
                source_id=source.id,
                status=payload.verification_status,
                checked_by_user_id=checked_by.id,
                notes=payload.notes,
            )
        )
        self.session.commit()
        self.session.refresh(opportunity)
        return self.to_admin_response(opportunity)

    def list_admin_opportunities(self, **filters: object) -> list[AdminOpportunityResponse]:
        return [
            self.to_admin_response(opportunity)
            for opportunity in self.repository.list_admin_opportunities(**filters)
        ]

    def list_public_opportunities(self, **filters: object) -> list[OpportunitySummaryResponse]:
        return [
            self.to_summary_response(opportunity)
            for opportunity in self.repository.list_public_opportunities(**filters)
        ]

    def get_public_opportunity(self, opportunity_id: uuid.UUID) -> OpportunityDetailResponse:
        opportunity = self.repository.get_opportunity(opportunity_id)
        if opportunity is None or self._official_source(opportunity) is None:
            raise AppError("opportunity_not_found", "Opportunity was not found", 404)
        if opportunity.status is not OpportunityStatus.ACTIVE:
            raise AppError("opportunity_not_found", "Opportunity was not found", 404)
        return self.to_detail_response(opportunity)

    def to_admin_response(self, opportunity: Opportunity) -> AdminOpportunityResponse:
        official_source = self._best_source(opportunity)
        return AdminOpportunityResponse(
            **self._response_base(opportunity, official_source, require_verified=False),
            sources=[SourceResponse.model_validate(source) for source in opportunity.sources],
        )

    def to_detail_response(self, opportunity: Opportunity) -> OpportunityDetailResponse:
        official_source = self._official_source(opportunity)
        if official_source is None:
            raise AppError("opportunity_not_found", "Opportunity was not found", 404)
        return OpportunityDetailResponse(
            **self._response_base(opportunity, official_source, require_verified=True)
        )

    def to_summary_response(self, opportunity: Opportunity) -> OpportunitySummaryResponse:
        official_source = self._official_source(opportunity)
        if official_source is None:
            raise AppError("source_not_verified", "Opportunity has no verified official source")
        return self._summary_response(opportunity, official_source)

    def _summary_response(
        self, opportunity: Opportunity, source: Source
    ) -> OpportunitySummaryResponse:
        return OpportunitySummaryResponse(
            id=opportunity.id,
            name=opportunity.name,
            provider_name=opportunity.provider.name,
            university_name=opportunity.university.name if opportunity.university else None,
            country=opportunity.country,
            degree_level=opportunity.degree_level,
            application_deadline=opportunity.application_deadline,
            funding_type=opportunity.funding_type,
            funding_summary=self._funding_summary(opportunity),
            verification_status=source.verification_status,
            last_verified_at=source.last_verified_at,
            official_source_url=source.url,
        )

    def _response_base(
        self, opportunity: Opportunity, source: Source, *, require_verified: bool
    ) -> dict[str, object]:
        summary = (
            self.to_summary_response(opportunity)
            if require_verified
            else self._summary_response(opportunity, source)
        )
        return {
            **summary.model_dump(),
            "field_eligibility": opportunity.field_eligibility,
            "nationality_eligibility": opportunity.nationality_eligibility,
            "intake_year": opportunity.intake_year,
            "tuition_coverage": opportunity.tuition_coverage,
            "monthly_stipend_amount": opportunity.monthly_stipend_amount,
            "monthly_stipend_currency": opportunity.monthly_stipend_currency,
            "accommodation_coverage": opportunity.accommodation_coverage,
            "travel_allowance": opportunity.travel_allowance,
            "health_insurance": opportunity.health_insurance,
            "application_fee_info": opportunity.application_fee_info,
            "english_language_requirement": opportunity.english_language_requirement,
            "standardized_test_requirement": opportunity.standardized_test_requirement,
            "minimum_academic_requirement": opportunity.minimum_academic_requirement,
            "required_documents": opportunity.required_documents,
            "application_method": opportunity.application_method,
            "application_url": opportunity.application_url,
            "status": opportunity.status,
            "data_confidence": opportunity.data_confidence,
            "notes": opportunity.notes,
            "eligibility_warnings": opportunity.eligibility_warnings,
            "source": SourceResponse.model_validate(source),
        }

    def _select_source(self, opportunity: Opportunity, source_id: uuid.UUID | None) -> Source:
        if source_id is None:
            if len(opportunity.sources) == 1:
                return opportunity.sources[0]
            raise AppError("source_required", "source_id is required when multiple sources exist")

        source = self.repository.get_source(source_id)
        if source is None or source.opportunity_id != opportunity.id:
            raise AppError("source_not_found", "Source was not found", 404)
        return source

    @staticmethod
    def _official_source(opportunity: Opportunity) -> Source | None:
        verified_sources = [
            source
            for source in opportunity.sources
            if source.source_type is SourceType.OFFICIAL
            and source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
        ]
        return max(
            verified_sources,
            key=lambda source: source.last_verified_at or source.date_collected,
            default=None,
        )

    @staticmethod
    def _best_source(opportunity: Opportunity) -> Source:
        official = OpportunityService._official_source(opportunity)
        if official is not None:
            return official
        return opportunity.sources[0]

    @staticmethod
    def _funding_summary(opportunity: Opportunity) -> str:
        parts: list[str] = [opportunity.funding_type.value.replace("_", " ")]
        if opportunity.tuition_coverage:
            parts.append(f"tuition: {opportunity.tuition_coverage}")
        if opportunity.monthly_stipend_amount is not None:
            parts.append(
                f"stipend: {opportunity.monthly_stipend_amount} "
                f"{opportunity.monthly_stipend_currency}"
            )
        if opportunity.accommodation_coverage:
            parts.append("accommodation mentioned")
        if opportunity.travel_allowance:
            parts.append("travel mentioned")
        return "; ".join(parts)

    @staticmethod
    def _prepare_import_row(raw_row: dict[str, object]) -> tuple[dict[str, object], list[str]]:
        prepared = dict(raw_row)
        warnings: list[str] = []

        if prepared.get("status") not in {
            None,
            OpportunityStatus.DRAFT.value,
            OpportunityStatus.DRAFT,
        }:
            warnings.append("Imported opportunities are forced to draft until human verification")
        prepared["status"] = OpportunityStatus.DRAFT.value

        source = dict(prepared.get("source") or {})
        if source.get("verification_status") not in {
            None,
            VerificationStatus.NEEDS_REVIEW.value,
            VerificationStatus.NEEDS_REVIEW,
        }:
            warnings.append("Imported sources are forced to needs_review until human verification")
        source["verification_status"] = VerificationStatus.NEEDS_REVIEW.value
        prepared["source"] = source
        return prepared, warnings

    @staticmethod
    def _validation_messages(exc: ValidationError) -> list[str]:
        messages: list[str] = []
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"])
            messages.append(f"{field}: {error['msg']}")
        return messages

    @staticmethod
    def _duplicate_key(payload: OpportunityCreate) -> tuple[str, str, str, int | None]:
        return (
            payload.provider_name.lower(),
            payload.name.lower(),
            payload.country.lower(),
            payload.intake_year,
        )

    @staticmethod
    def _data_quality_warnings(payload: OpportunityCreate) -> list[str]:
        warnings: list[str] = []
        if payload.application_deadline is None:
            warnings.append("Missing application deadline")
        if payload.funding_type.value == "unknown":
            warnings.append("Funding type is unknown")
        if not payload.required_documents:
            warnings.append("No required documents listed")
        if payload.english_language_requirement is None:
            warnings.append("English-language requirement is missing")
        if payload.minimum_academic_requirement is None:
            warnings.append("Minimum academic requirement is missing")
        if payload.data_confidence.value == "low":
            warnings.append("Data confidence is low; curator review is important")
        return warnings
