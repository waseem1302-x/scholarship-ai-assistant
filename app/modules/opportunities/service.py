import csv
import io
import re
import uuid
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError
from app.modules.auth.models import AuditLog, User
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.lifecycle import (
    SOURCE_FRESHNESS_DAYS,
    effective_application_window,
    materialize_catalogue_window,
)
from app.modules.opportunities.models import (
    ApplicationWindowState,
    DuplicateSuggestion,
    DuplicateSuggestionStatus,
    EligibilityRule,
    EligibilityRuleType,
    EligibilityRuleValue,
    FundingClassification,
    FundingCoverageStatus,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Source,
    SourceExcerpt,
    SourceType,
    VerificationRecord,
    VerificationStatus,
)
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.schemas import (
    AdminOpportunityResponse,
    AdminOpportunitySearchResponse,
    CatalogueDecisionTier,
    DataQualityIssueResponse,
    DataQualityIssueSearchResponse,
    DataQualitySeverity,
    DuplicateSuggestionDecision,
    DuplicateSuggestionResponse,
    DuplicateSuggestionSearchResponse,
    EligibilityRuleCreate,
    ImportRowStatus,
    OpportunityCreate,
    OpportunityDetailResponse,
    OpportunityImportRequest,
    OpportunityImportResponse,
    OpportunityImportRowResult,
    OpportunitySearchResponse,
    OpportunitySummaryResponse,
    PaginationMeta,
    ReviewAction,
    ReviewActionRequest,
    ReviewQueueItemResponse,
    ReviewQueueResponse,
    SourceCheckRequest,
    SourceCheckResponse,
    SourceExcerptResponse,
    SourceResponse,
    VerificationFreshness,
    VerificationUpdate,
)

CSV_COLUMN_ALIASES = {
    "official_source_url": "source.url",
    "source_url": "source.url",
    "source_title": "source.title",
    "source_excerpt": "source.relevant_excerpt",
    "source_relevant_excerpt": "source.relevant_excerpt",
    "source_type": "source.source_type",
    "source_publication_date": "source.publication_date",
    "source_content_hash": "source.content_hash",
    "source_verification_status": "source.verification_status",
}
CSV_LIST_FIELDS = {"required_documents", "eligibility_warnings"}


class OpportunityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OpportunityRepository(session)

    def create_opportunity(
        self, payload: OpportunityCreate, *, created_by: User
    ) -> AdminOpportunityResponse:
        try:
            return self._create_opportunity(payload, created_by=created_by, commit=True)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "duplicate_opportunity",
                "An opportunity with the same provider, name, country, and intake already exists",
            ) from exc

    def _create_opportunity(
        self, payload: OpportunityCreate, *, created_by: User, commit: bool
    ) -> AdminOpportunityResponse:
        if payload.status is OpportunityStatus.ACTIVE:
            raise AppError(
                "record_publish_action_required",
                "New opportunities must be reviewed and published through a review action",
                422,
            )
        if payload.eligibility_rules and payload.source.source_type is not SourceType.OFFICIAL:
            raise AppError(
                "eligibility_rule_official_source_required",
                "Eligibility rules require an official source and immutable source excerpt",
                422,
            )
        if any(
            rule.source_id is not None or rule.source_excerpt_id is not None
            for rule in payload.eligibility_rules
        ):
            raise AppError(
                "eligibility_rule_source_reference_invalid",
                "New opportunity rules must use the official source supplied with the opportunity",
                422,
            )
        provider = self.repository.get_or_create_provider(
            payload.provider_name,
            str(payload.provider_website_url) if payload.provider_website_url else None,
            payload.provider_canonical_id or self._canonical_identifier(payload.provider_name),
        )
        programme_family_id = payload.programme_family_id or self._canonical_identifier(
            payload.name
        )
        cycle_id = payload.cycle_id or (str(payload.intake_year) if payload.intake_year else None)
        if self.repository.find_duplicate_by_canonical_identity(
            provider_id=provider.id,
            programme_family_id=programme_family_id,
            cycle_id=cycle_id,
            degree_level=payload.degree_level,
            funding_type=payload.funding_type,
        ):
            raise ConflictError(
                "duplicate_opportunity",
                "An opportunity with the same canonical provider, programme family, cycle, "
                "degree, and funding already exists",
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
            programme_family_id=programme_family_id,
            cycle_id=cycle_id,
            country=payload.country,
            degree_level=payload.degree_level,
            field_eligibility=payload.field_eligibility,
            nationality_eligibility=payload.nationality_eligibility,
            application_opening_date=payload.application_opening_date,
            application_deadline=payload.application_deadline,
            intake_year=payload.intake_year,
            funding_type=payload.funding_type,
            funding_classification=self._funding_classification(payload),
            funding_policy=payload.funding_policy,
            tuition_coverage_status=payload.tuition_coverage_status,
            stipend_coverage_status=payload.stipend_coverage_status,
            accommodation_coverage_status=payload.accommodation_coverage_status,
            travel_coverage_status=payload.travel_coverage_status,
            insurance_coverage_status=payload.insurance_coverage_status,
            fees_coverage_status=payload.fees_coverage_status,
            application_fee_status=payload.application_fee_status,
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
        source = Source(
            url=str(payload.source.url),
            canonical_url=self.repository.canonicalize_url(str(payload.source.url)),
            source_type=payload.source.source_type,
            title=payload.source.title.strip(),
            publication_date=payload.source.publication_date,
            hash_algorithm=payload.source.hash_algorithm,
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
        opportunity.sources.append(source)
        for cycle in payload.application_cycles:
            opportunity.cycles.append(
                OpportunityCycle(
                    intake_year=cycle.intake_year,
                    application_opening_date=cycle.application_opening_date,
                    application_deadline=cycle.application_deadline,
                    timezone=cycle.timezone,
                    is_rolling=cycle.is_rolling,
                    is_archived=cycle.is_archived,
                )
            )
        materialize_catalogue_window(opportunity)
        self.repository.add_opportunity(opportunity)
        self.session.flush()
        self.repository.create_duplicate_suggestions(opportunity)
        if payload.eligibility_rules:
            excerpt = SourceExcerpt(
                source_id=source.id,
                text=source.relevant_excerpt,
                hash_algorithm=source.hash_algorithm,
                content_hash=source.content_hash,
                captured_by_user_id=created_by.id,
            )
            self.session.add(excerpt)
            self.session.flush()
            for rule in payload.eligibility_rules:
                eligibility_rule = EligibilityRule(
                    rule_type=rule.rule_type,
                    operator=rule.operator,
                    value_json=rule.value,
                    unit=rule.unit,
                    grading_scale=rule.grading_scale,
                    required=rule.required,
                    source_id=source.id,
                    source_excerpt_id=excerpt.id,
                    confidence=rule.confidence,
                    curator_notes=rule.curator_notes,
                )
                eligibility_rule.value_keys = [
                    EligibilityRuleValue(value_key=value_key)
                    for value_key in self._eligibility_value_keys(rule)
                ]
                opportunity.eligibility_rules.append(eligibility_rule)
        self.session.add(
            AuditLog(
                actor_user_id=created_by.id,
                action="opportunity_created",
                entity_type="opportunity",
                entity_id=str(opportunity.id),
            )
        )

        if commit:
            self.session.commit()
        self.session.refresh(opportunity)
        return self.to_admin_response(opportunity)

    def import_opportunities(
        self, payload: OpportunityImportRequest, *, created_by: User
    ) -> OpportunityImportResponse:
        results: list[OpportunityImportRowResult] = []
        seen_keys: set[tuple[str, str, str, int | None]] = set()
        import_rows = self._import_rows(payload)

        for row_number, raw_row, row_warnings in import_rows:
            prepared_row, preparation_warnings = self._prepare_import_row(raw_row)
            try:
                opportunity_payload = OpportunityCreate.model_validate(prepared_row)
            except ValidationError as exc:
                results.append(
                    OpportunityImportRowResult(
                        row_number=row_number,
                        status=ImportRowStatus.FAILED_VALIDATION,
                        errors=self._validation_messages(exc),
                        warnings=row_warnings + preparation_warnings,
                    )
                )
                continue

            warnings = (
                row_warnings
                + preparation_warnings
                + self._data_quality_warnings(opportunity_payload)
            )
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
                # A row error rolls back only that row. All accepted rows share
                # the outer transaction and are committed once after the batch.
                with self.session.begin_nested():
                    created = self._create_opportunity(
                        opportunity_payload, created_by=created_by, commit=False
                    )
            except (AppError, IntegrityError) as exc:
                results.append(
                    OpportunityImportRowResult(
                        row_number=row_number,
                        status=ImportRowStatus.FAILED_VALIDATION,
                        errors=[
                            exc.message
                            if isinstance(exc, AppError)
                            else "Opportunity conflicts with an existing catalogue record"
                        ],
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

        if not payload.dry_run and any(
            result.status is ImportRowStatus.IMPORTED for result in results
        ):
            self.session.commit()

        return OpportunityImportResponse(
            source_format=payload.source_format,
            dry_run=payload.dry_run,
            total_rows=len(import_rows),
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
        self,
        opportunity_id: uuid.UUID,
        payload: VerificationUpdate,
        *,
        checked_by: User,
    ) -> AdminOpportunityResponse:
        opportunity = self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise AppError("opportunity_not_found", "Opportunity was not found", 404)

        source = self._select_source(opportunity, payload.source_id)
        source.verification_status = payload.verification_status
        source.verified_by_user_id = checked_by.id
        if payload.verification_status is VerificationStatus.OFFICIALLY_VERIFIED:
            source.last_verified_at = datetime.now(UTC)
        elif payload.verification_status is VerificationStatus.EXPIRED:
            opportunity.status = OpportunityStatus.EXPIRED
        elif payload.verification_status in {
            VerificationStatus.NEEDS_REVIEW,
            VerificationStatus.UNVERIFIED,
            VerificationStatus.CONFLICTING_INFORMATION,
        }:
            opportunity.status = OpportunityStatus.DRAFT

        self.session.add(
            VerificationRecord(
                opportunity_id=opportunity.id,
                source_id=source.id,
                status=payload.verification_status,
                checked_by_user_id=checked_by.id,
                notes=payload.notes,
            )
        )
        self.session.add(
            AuditLog(
                actor_user_id=checked_by.id,
                action="source_verification_updated",
                entity_type="opportunity",
                entity_id=str(opportunity.id),
                metadata_json={"verification_status": payload.verification_status.value},
            )
        )
        self.session.commit()
        self.session.refresh(opportunity)
        return self.to_admin_response(opportunity)

    def apply_review_action(
        self,
        opportunity_id: uuid.UUID,
        payload: ReviewActionRequest,
        *,
        reviewed_by: User,
    ) -> AdminOpportunityResponse:
        opportunity = self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise AppError("opportunity_not_found", "Opportunity was not found", 404)

        source = self._select_source(opportunity, payload.source_id)
        self._validate_review_action(payload)

        status = self._apply_review_transition(opportunity, source, payload, reviewed_by)
        self.session.add(
            VerificationRecord(
                opportunity_id=opportunity.id,
                source_id=source.id,
                status=status,
                checked_by_user_id=reviewed_by.id,
                notes=payload.notes,
                metadata_json={
                    "action": payload.action.value,
                    "opportunity_status": opportunity.status.value,
                    "source_status": source.verification_status.value,
                },
            )
        )
        self.session.add(
            AuditLog(
                actor_user_id=reviewed_by.id,
                action="opportunity_review_action",
                entity_type="opportunity",
                entity_id=str(opportunity.id),
                metadata_json={
                    "review_action": payload.action.value,
                    "source_id": str(source.id),
                    "opportunity_status": opportunity.status.value,
                    "source_status": source.verification_status.value,
                },
            )
        )
        self.session.commit()
        self.session.refresh(opportunity)
        return self.to_admin_response(opportunity)

    def record_source_check(
        self,
        source_id: uuid.UUID,
        payload: SourceCheckRequest,
        *,
        checked_by: User | None,
    ) -> SourceCheckResponse:
        source = self.repository.get_source(source_id)
        if source is None:
            raise AppError("source_not_found", "Source was not found", 404)

        previous_hash = source.content_hash
        changed = (
            payload.content_hash is not None
            and previous_hash is not None
            and payload.content_hash != previous_hash
        )
        if payload.content_hash is not None:
            source.hash_algorithm = payload.hash_algorithm
            source.content_hash = payload.content_hash
        source.last_updated_at = payload.observed_at or datetime.now(UTC)

        captured_excerpt: SourceExcerpt | None = None
        if payload.excerpt is not None:
            captured_excerpt = SourceExcerpt(
                source_id=source.id,
                section_label=payload.excerpt.section_label,
                locator=payload.excerpt.locator,
                text=payload.excerpt.text,
                hash_algorithm=(
                    payload.excerpt.hash_algorithm
                    if payload.excerpt.content_hash is not None
                    else payload.hash_algorithm
                ),
                content_hash=payload.excerpt.content_hash or payload.content_hash,
                captured_by_user_id=checked_by.id if checked_by else None,
            )
            self.session.add(captured_excerpt)

        if changed:
            source.verification_status = VerificationStatus.NEEDS_REVIEW

        status = VerificationStatus.NEEDS_REVIEW if changed else source.verification_status
        self.session.add(
            VerificationRecord(
                opportunity_id=source.opportunity_id,
                source_id=source.id,
                status=status,
                checked_by_user_id=checked_by.id if checked_by else None,
                notes=payload.change_summary,
                metadata_json={
                    "action": "source_check_recorded",
                    "changed": changed,
                    "previous_hash": previous_hash,
                    "current_hash": source.content_hash,
                    "observed_at": (payload.observed_at or source.last_updated_at).isoformat(),
                },
            )
        )
        self.session.add(
            AuditLog(
                actor_user_id=checked_by.id if checked_by else None,
                action="source_check_recorded",
                entity_type="source",
                entity_id=str(source.id),
                metadata_json={
                    "changed": changed,
                    "opportunity_id": str(source.opportunity_id),
                },
            )
        )
        self.session.commit()
        self.session.refresh(source)
        if captured_excerpt is not None:
            self.session.refresh(captured_excerpt)

        return SourceCheckResponse(
            source=SourceResponse.model_validate(source),
            changed=changed,
            previous_hash=previous_hash,
            current_hash=source.content_hash,
            public_visibility_blocked=not self._source_can_publish(source),
            excerpt=(
                SourceExcerptResponse.model_validate(captured_excerpt)
                if captured_excerpt is not None
                else None
            ),
        )

    def list_admin_opportunities(
        self, *, limit: int, offset: int, **filters: object
    ) -> AdminOpportunitySearchResponse:
        opportunities = self.repository.list_admin_opportunities(
            **filters, limit=limit, offset=offset
        )
        total = self.repository.count_admin_opportunities(**filters)
        items = [self.to_admin_response(opportunity) for opportunity in opportunities]
        return AdminOpportunitySearchResponse(
            items=items,
            pagination=self._pagination(total=total, limit=limit, offset=offset, count=len(items)),
        )

    def list_data_quality_issues(
        self, *, limit: int, offset: int
    ) -> DataQualityIssueSearchResponse:
        page = [
            DataQualityIssueResponse.model_validate(issue)
            for issue in self.repository.list_data_quality_issues(limit=limit, offset=offset)
        ]
        total = self.repository.count_data_quality_issues()
        return DataQualityIssueSearchResponse(
            items=page,
            pagination=self._pagination(total=total, limit=limit, offset=offset, count=len(page)),
        )

    def list_review_queue(self, *, limit: int, offset: int) -> ReviewQueueResponse:
        opportunities = self.repository.list_review_queue_opportunities(limit=limit, offset=offset)
        issues_by_opportunity: dict[uuid.UUID, list[DataQualityIssueResponse]] = {}
        for issue in self.repository.list_data_quality_issues_for_opportunities(
            [opportunity.id for opportunity in opportunities]
        ):
            response = DataQualityIssueResponse.model_validate(issue)
            if response.severity in {DataQualitySeverity.HIGH, DataQualitySeverity.MEDIUM}:
                issues_by_opportunity.setdefault(response.opportunity_id, []).append(response)
        items = [
            ReviewQueueItemResponse(
                opportunity=self.to_admin_response(opportunity),
                reasons=self._sorted_issues(issues_by_opportunity[opportunity.id]),
            )
            for opportunity in opportunities
        ]
        total = self.repository.count_review_queue_opportunities()
        return ReviewQueueResponse(
            items=items,
            pagination=self._pagination(total=total, limit=limit, offset=offset, count=len(items)),
        )

    def list_public_opportunities(
        self, *, limit: int, offset: int, **filters: object
    ) -> OpportunitySearchResponse:
        open_now = bool(filters.pop("open_now", False))
        application_window_state = filters.pop("application_window_state", None)
        if application_window_state is not None and not isinstance(
            application_window_state, ApplicationWindowState
        ):
            raise AppError(
                "application_window_state_invalid",
                "Application window state is not valid",
                422,
            )
        if open_now and application_window_state is not None:
            raise AppError(
                "application_window_filter_conflict",
                "Open-now and application-window-state filters cannot be combined",
                422,
            )

        opportunities = self.repository.list_public_opportunities(
            **filters,
            open_now=open_now,
            application_window_state=application_window_state,
            limit=limit,
            offset=offset,
        )
        total = self.repository.count_public_opportunities(
            **filters,
            open_now=open_now,
            application_window_state=application_window_state,
        )
        items = [self.to_summary_response(opportunity) for opportunity in opportunities]
        return OpportunitySearchResponse(
            items=items,
            pagination=self._pagination(total=total, limit=limit, offset=offset, count=len(items)),
        )

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
            raise AppError(
                "source_not_verified",
                "Opportunity has no verified official source",
            )
        return self._summary_response(opportunity, official_source)

    def to_private_application_summary_response(
        self, opportunity: Opportunity
    ) -> OpportunitySummaryResponse:
        """Preserve owner-visible application context if public verification changes."""
        source = self._official_source(opportunity) or next(
            (item for item in opportunity.sources if item.source_type is SourceType.OFFICIAL),
            None,
        )
        if source is None:
            source = next(iter(opportunity.sources), None)
        if source is None:
            raise AppError(
                "application_source_missing",
                "Application source record was not found",
                404,
            )
        return self._summary_response(opportunity, source)

    def _summary_response(
        self, opportunity: Opportunity, source: Source
    ) -> OpportunitySummaryResponse:
        window = effective_application_window(opportunity, source)
        structured_eligibility_complete = self._structured_eligibility_complete(opportunity)
        return OpportunitySummaryResponse(
            id=opportunity.id,
            name=opportunity.name,
            provider_name=opportunity.provider.name,
            university_name=opportunity.university.name if opportunity.university else None,
            country=opportunity.country,
            degree_level=opportunity.degree_level,
            application_deadline=window.application_deadline,
            application_opening_date=window.application_opening_date,
            application_timezone=window.timezone,
            effective_cycle_id=window.cycle.id if window.cycle else None,
            funding_type=opportunity.funding_type,
            funding_classification=opportunity.funding_classification,
            funding_summary=self._funding_summary(opportunity),
            verification_status=source.verification_status,
            last_verified_at=source.last_verified_at,
            official_source_url=source.url,
            application_window_state=window.state,
            source_is_fresh=window.source_is_fresh,
            verification_freshness=self._verification_freshness(source),
            funding_display_label=self._funding_display_label(opportunity),
            catalogue_decision_tier=(
                CatalogueDecisionTier.DECISION_READY
                if structured_eligibility_complete
                else CatalogueDecisionTier.INFORMATIONAL_ONLY
            ),
            structured_eligibility_complete=structured_eligibility_complete,
        )

    @staticmethod
    def _structured_eligibility_complete(opportunity: Opportunity) -> bool:
        structured_types = {rule.rule_type for rule in opportunity.eligibility_rules}
        if not structured_types:
            return False
        dependencies: list[tuple[str | None, set[EligibilityRuleType]]] = [
            (opportunity.field_eligibility, {EligibilityRuleType.FIELD}),
            (opportunity.nationality_eligibility, {EligibilityRuleType.NATIONALITY}),
            (
                opportunity.minimum_academic_requirement,
                {EligibilityRuleType.CGPA, EligibilityRuleType.PERCENTAGE},
            ),
            (
                opportunity.english_language_requirement,
                {
                    EligibilityRuleType.ENGLISH_TEST_STATUS,
                    EligibilityRuleType.IELTS,
                    EligibilityRuleType.TOEFL,
                    EligibilityRuleType.DUOLINGO,
                },
            ),
            (opportunity.standardized_test_requirement, {EligibilityRuleType.GRE}),
        ]
        return all(not text or bool(structured_types & required) for text, required in dependencies)

    @staticmethod
    def _verification_freshness(source: Source) -> VerificationFreshness:
        if source.last_verified_at is None:
            return VerificationFreshness.HISTORICAL
        age = datetime.now(UTC) - (
            source.last_verified_at.replace(tzinfo=UTC)
            if source.last_verified_at.tzinfo is None
            else source.last_verified_at.astimezone(UTC)
        )
        if age <= timedelta(days=SOURCE_FRESHNESS_DAYS):
            return VerificationFreshness.RECENT
        if age <= timedelta(days=SOURCE_FRESHNESS_DAYS * 2):
            return VerificationFreshness.RECHECK_RECOMMENDED
        return VerificationFreshness.HISTORICAL

    @staticmethod
    def _funding_display_label(opportunity: Opportunity) -> str:
        if opportunity.funding_classification is FundingClassification.FULLY_FUNDED:
            return "All tracked funding components confirmed"
        if opportunity.funding_classification is FundingClassification.PARTIAL:
            return "Some funding components confirmed"
        return "Funding coverage requires verification"

    def _response_base(
        self,
        opportunity: Opportunity,
        source: Source,
        *,
        require_verified: bool,
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
            "funding_policy": opportunity.funding_policy,
            "tuition_coverage_status": opportunity.tuition_coverage_status,
            "stipend_coverage_status": opportunity.stipend_coverage_status,
            "accommodation_coverage_status": opportunity.accommodation_coverage_status,
            "travel_coverage_status": opportunity.travel_coverage_status,
            "insurance_coverage_status": opportunity.insurance_coverage_status,
            "fees_coverage_status": opportunity.fees_coverage_status,
            "application_fee_status": opportunity.application_fee_status,
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
            "eligibility_rules": [
                EligibilityRuleCreate(
                    rule_type=rule.rule_type,
                    operator=rule.operator,
                    value=rule.value_json,
                    unit=rule.unit,
                    grading_scale=rule.grading_scale,
                    required=rule.required,
                    source_id=rule.source_id,
                    source_excerpt_id=rule.source_excerpt_id,
                    confidence=rule.confidence,
                    curator_notes=rule.curator_notes,
                )
                for rule in opportunity.eligibility_rules
            ],
        }

    def _select_source(self, opportunity: Opportunity, source_id: uuid.UUID | None) -> Source:
        if source_id is None:
            if len(opportunity.sources) == 1:
                return opportunity.sources[0]
            raise AppError(
                "source_required",
                "source_id is required when multiple sources exist",
            )

        source = self.repository.get_source(source_id)
        if source is None or source.opportunity_id != opportunity.id:
            raise AppError("source_not_found", "Source was not found", 404)
        return source

    @staticmethod
    def _validate_review_action(payload: ReviewActionRequest) -> None:
        note_required_actions = {
            ReviewAction.HOLD_FOR_REVIEW,
            ReviewAction.FLAG_CONFLICT,
            ReviewAction.REQUEST_RECHECK,
            ReviewAction.RESOLVE_CONFLICT,
            ReviewAction.EXPIRE,
            ReviewAction.ARCHIVE,
        }
        if payload.action in note_required_actions and not (payload.notes or "").strip():
            raise AppError(
                "review_notes_required",
                "Reviewer notes are required for this action",
                422,
            )

    @staticmethod
    def _apply_review_transition(
        opportunity: Opportunity,
        source: Source,
        payload: ReviewActionRequest,
        reviewed_by: User,
    ) -> VerificationStatus:
        now = datetime.now(UTC)

        if payload.action is ReviewAction.PUBLISH:
            source.verification_status = VerificationStatus.OFFICIALLY_VERIFIED
            source.verified_by_user_id = reviewed_by.id
            source.last_verified_at = now
            opportunity.status = OpportunityStatus.ACTIVE
            return VerificationStatus.OFFICIALLY_VERIFIED

        if payload.action is ReviewAction.RESOLVE_CONFLICT:
            source.verification_status = VerificationStatus.OFFICIALLY_VERIFIED
            source.verified_by_user_id = reviewed_by.id
            source.last_verified_at = now
            opportunity.status = OpportunityStatus.ACTIVE
            return VerificationStatus.OFFICIALLY_VERIFIED

        if payload.action is ReviewAction.HOLD_FOR_REVIEW:
            source.verification_status = VerificationStatus.NEEDS_REVIEW
            opportunity.status = OpportunityStatus.DRAFT
            return VerificationStatus.NEEDS_REVIEW

        if payload.action is ReviewAction.REQUEST_RECHECK:
            source.verification_status = VerificationStatus.NEEDS_REVIEW
            opportunity.status = OpportunityStatus.DRAFT
            return VerificationStatus.NEEDS_REVIEW

        if payload.action is ReviewAction.FLAG_CONFLICT:
            source.verification_status = VerificationStatus.CONFLICTING_INFORMATION
            opportunity.status = OpportunityStatus.DRAFT
            return VerificationStatus.CONFLICTING_INFORMATION

        if payload.action is ReviewAction.EXPIRE:
            source.verification_status = VerificationStatus.EXPIRED
            opportunity.status = OpportunityStatus.EXPIRED
            return VerificationStatus.EXPIRED

        if payload.action is ReviewAction.ARCHIVE:
            source.verification_status = VerificationStatus.ARCHIVED
            opportunity.status = OpportunityStatus.ARCHIVED
            return VerificationStatus.ARCHIVED

        raise AppError("unsupported_review_action", "Review action is not supported", 422)

    @staticmethod
    def _official_source(opportunity: Opportunity) -> Source | None:
        return EvidencePolicy.select_current_official_source(opportunity.sources)

    @staticmethod
    def _best_source(opportunity: Opportunity) -> Source:
        return EvidencePolicy.select_review_source(opportunity.sources) or opportunity.sources[0]

    @staticmethod
    def _funding_summary(opportunity: Opportunity) -> str:
        parts: list[str] = [opportunity.funding_classification.value.replace("_", " ")]
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
    def _funding_classification(payload: OpportunityCreate) -> FundingClassification:
        components = [
            payload.tuition_coverage_status,
            payload.stipend_coverage_status,
            payload.accommodation_coverage_status,
            payload.travel_coverage_status,
            payload.insurance_coverage_status,
            payload.fees_coverage_status,
        ]
        if payload.funding_policy and all(
            component is FundingCoverageStatus.CONFIRMED for component in components
        ):
            return FundingClassification.FULLY_FUNDED
        if any(component is not FundingCoverageStatus.UNKNOWN for component in components):
            return FundingClassification.PARTIAL
        if payload.funding_type.value in {"partial", "tuition_only", "stipend_only"}:
            return FundingClassification.PARTIAL
        return FundingClassification.UNKNOWN

    @classmethod
    def _eligibility_value_keys(cls, rule: EligibilityRuleCreate) -> list[str]:
        textual_rule_types = {
            EligibilityRuleType.NATIONALITY,
            EligibilityRuleType.RESIDENCE,
            EligibilityRuleType.TARGET_DEGREE,
            EligibilityRuleType.FIELD,
            EligibilityRuleType.APPLICATION_WINDOW,
            EligibilityRuleType.STUDY_MODE,
            EligibilityRuleType.CURRENT_EDUCATION_LEVEL,
            EligibilityRuleType.ENGLISH_TEST_STATUS,
            EligibilityRuleType.GRE_STATUS,
        }
        if rule.rule_type not in textual_rule_types:
            return []

        values = rule.value if isinstance(rule.value, list) else [rule.value]
        return sorted(
            {
                OpportunityRepository.structured_value_key(value)
                for value in values
                if isinstance(value, str) and OpportunityRepository.structured_value_key(value)
            }
        )

    def _import_rows(
        self, payload: OpportunityImportRequest
    ) -> list[tuple[int, dict[str, object], list[str]]]:
        if payload.source_format.value == "csv":
            return self._csv_import_rows(payload.csv_content or "")
        return [(row_number, row, []) for row_number, row in enumerate(payload.rows, start=1)]

    @classmethod
    def _csv_import_rows(cls, csv_content: str) -> list[tuple[int, dict[str, object], list[str]]]:
        try:
            reader = csv.DictReader(io.StringIO(csv_content.lstrip("\ufeff")))
        except csv.Error as exc:
            raise AppError("csv_import_invalid", f"CSV could not be parsed: {exc}", 422) from exc

        if not reader.fieldnames:
            raise AppError("csv_import_invalid", "CSV must include a header row", 422)

        fieldnames = [cls._csv_header_name(name) for name in reader.fieldnames]
        if any(not name for name in fieldnames):
            raise AppError("csv_import_invalid", "CSV headers cannot be blank", 422)
        if len(set(fieldnames)) != len(fieldnames):
            raise AppError("csv_import_invalid", "CSV headers must be unique", 422)

        rows: list[tuple[int, dict[str, object], list[str]]] = []
        for csv_index, raw_row in enumerate(reader, start=2):
            mapped, warnings = cls._csv_row_to_import_row(raw_row)
            if not mapped:
                continue
            rows.append((csv_index, mapped, warnings))
            if len(rows) > 100:
                raise AppError(
                    "csv_import_too_large",
                    "CSV imports are limited to 100 rows",
                    422,
                )

        if not rows:
            raise AppError(
                "csv_import_invalid",
                "CSV must include at least one data row",
                422,
            )
        return rows

    @classmethod
    def _csv_row_to_import_row(
        cls, raw_row: dict[str, str | None]
    ) -> tuple[dict[str, object], list[str]]:
        row: dict[str, object] = {}
        source: dict[str, object] = {"source_type": SourceType.OFFICIAL.value}
        warnings: list[str] = []

        for header, raw_value in raw_row.items():
            key = cls._csv_header_name(header)
            value, cell_warning = cls._clean_csv_cell(raw_value)
            if cell_warning:
                warnings.append(f"{key}: {cell_warning}")
            if value is None:
                continue
            target = CSV_COLUMN_ALIASES.get(key, key)
            if target in CSV_LIST_FIELDS:
                row[target] = cls._csv_list(value)
            elif target.startswith("source."):
                source[target.removeprefix("source.")] = value
            else:
                row[target] = value

        if any(value for key, value in source.items() if key != "source_type"):
            source.setdefault("verification_status", VerificationStatus.NEEDS_REVIEW.value)
            row["source"] = source

        component_fields = (
            "tuition_coverage_status",
            "stipend_coverage_status",
            "accommodation_coverage_status",
            "travel_coverage_status",
            "insurance_coverage_status",
            "fees_coverage_status",
        )
        if row.get("funding_type") == "full" and not all(
            row.get(field) == FundingCoverageStatus.CONFIRMED.value for field in component_fields
        ):
            row["funding_type"] = "unknown"
            warnings.append(
                "Imported full-funding claim was set to unknown until every component is verified"
            )
        return row, warnings

    @staticmethod
    def _csv_header_name(value: str | None) -> str:
        return (value or "").strip().lower().replace(" ", "_").replace("-", "_")

    @staticmethod
    def _clean_csv_cell(value: str | None) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        cleaned = value.strip()
        if cleaned == "":
            return None, None
        if cleaned[0] in {"=", "+", "-", "@"}:
            return f"'{cleaned}", "Formula-like value was neutralized"
        return cleaned, None

    @staticmethod
    def _csv_list(value: str) -> list[str]:
        return [item.strip() for item in value.split(";") if item.strip()]

    @staticmethod
    def _prepare_import_row(
        raw_row: dict[str, object],
    ) -> tuple[dict[str, object], list[str]]:
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
    def _duplicate_key(
        payload: OpportunityCreate,
    ) -> tuple[str, str, str, int | None]:
        return (
            payload.provider_name.lower(),
            payload.name.lower(),
            payload.country.lower(),
            payload.intake_year,
        )

    def list_duplicate_suggestions(
        self, *, limit: int, offset: int
    ) -> DuplicateSuggestionSearchResponse:
        suggestions = self.repository.list_duplicate_suggestions(limit=limit, offset=offset)
        total = self.repository.count_duplicate_suggestions()
        return DuplicateSuggestionSearchResponse(
            items=[self._duplicate_suggestion_response(suggestion) for suggestion in suggestions],
            pagination=self._pagination(
                total=total, limit=limit, offset=offset, count=len(suggestions)
            ),
        )

    def review_duplicate_suggestion(
        self, suggestion_id: uuid.UUID, payload: DuplicateSuggestionDecision, *, reviewed_by: User
    ) -> DuplicateSuggestionResponse:
        suggestion = self.repository.get_duplicate_suggestion(suggestion_id)
        if suggestion is None:
            raise AppError(
                "duplicate_suggestion_not_found", "Duplicate suggestion was not found", 404
            )
        suggestion.status = (
            DuplicateSuggestionStatus.CONFIRMED_DUPLICATE
            if payload.is_duplicate
            else DuplicateSuggestionStatus.DISMISSED
        )
        suggestion.reviewed_by_user_id = reviewed_by.id
        suggestion.reviewed_at = datetime.now(UTC)
        self.session.add(
            AuditLog(
                actor_user_id=reviewed_by.id,
                action="duplicate_suggestion_reviewed",
                entity_type="duplicate_suggestion",
                entity_id=str(suggestion.id),
                metadata_json={"is_duplicate": payload.is_duplicate},
            )
        )
        self.session.commit()
        self.session.refresh(suggestion)
        return self._duplicate_suggestion_response(suggestion)

    @staticmethod
    def _canonical_identifier(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
        return normalized[:120] or "catalogue-record"

    @staticmethod
    def _duplicate_suggestion_response(
        suggestion: DuplicateSuggestion,
    ) -> DuplicateSuggestionResponse:
        return DuplicateSuggestionResponse(
            id=suggestion.id,
            opportunity_id=suggestion.opportunity_id,
            opportunity_name=suggestion.opportunity.name,
            matched_opportunity_id=suggestion.matched_opportunity_id,
            matched_opportunity_name=suggestion.matched_opportunity.name,
            score=suggestion.score,
            status=suggestion.status,
            created_at=suggestion.created_at,
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

    def _data_quality_issues_for_opportunity(
        self, opportunity: Opportunity
    ) -> list[DataQualityIssueResponse]:
        issues: list[DataQualityIssueResponse] = []
        best_source = self._best_source(opportunity) if opportunity.sources else None

        if not opportunity.sources:
            issues.append(
                self._issue(
                    opportunity,
                    code="official_source_missing",
                    severity=DataQualitySeverity.HIGH,
                    message="Opportunity has no source evidence attached.",
                )
            )
        for source in opportunity.sources:
            if source.verification_status in {
                VerificationStatus.UNVERIFIED,
                VerificationStatus.NEEDS_REVIEW,
            }:
                issues.append(
                    self._issue(
                        opportunity,
                        source=source,
                        code="source_requires_review",
                        severity=DataQualitySeverity.HIGH,
                        message="Source is not verified and requires curator review.",
                    )
                )
            if source.verification_status is VerificationStatus.CONFLICTING_INFORMATION:
                issues.append(
                    self._issue(
                        opportunity,
                        source=source,
                        code="source_conflict",
                        severity=DataQualitySeverity.HIGH,
                        message="Source has conflicting information that must be resolved.",
                    )
                )
            if source.last_verified_at is None:
                issues.append(
                    self._issue(
                        opportunity,
                        source=source,
                        code="source_never_verified",
                        severity=DataQualitySeverity.MEDIUM,
                        message="Source has no recorded verification timestamp.",
                    )
                )
            elif self._as_utc(source.last_verified_at) < datetime.now(UTC) - timedelta(
                days=SOURCE_FRESHNESS_DAYS
            ):
                issues.append(
                    self._issue(
                        opportunity,
                        source=source,
                        code="source_stale",
                        severity=DataQualitySeverity.HIGH,
                        message=(
                            f"Source has not been reverified within {SOURCE_FRESHNESS_DAYS} days."
                        ),
                    )
                )
            if source.content_hash is None:
                issues.append(
                    self._issue(
                        opportunity,
                        source=source,
                        code="source_hash_missing",
                        severity=DataQualitySeverity.LOW,
                        message="Source has no stored content hash for change monitoring.",
                    )
                )

        if opportunity.application_deadline is None:
            issues.append(
                self._issue(
                    opportunity,
                    source=best_source,
                    code="deadline_missing",
                    severity=DataQualitySeverity.HIGH,
                    message="Application deadline is missing or unknown.",
                )
            )
        if not opportunity.required_documents:
            issues.append(
                self._issue(
                    opportunity,
                    source=best_source,
                    code="required_documents_missing",
                    severity=DataQualitySeverity.MEDIUM,
                    message="Required documents are not structured.",
                )
            )
        if opportunity.english_language_requirement is None:
            issues.append(
                self._issue(
                    opportunity,
                    source=best_source,
                    code="english_requirement_missing",
                    severity=DataQualitySeverity.MEDIUM,
                    message="English-language requirement is missing.",
                )
            )
        if opportunity.minimum_academic_requirement is None:
            issues.append(
                self._issue(
                    opportunity,
                    source=best_source,
                    code="academic_requirement_missing",
                    severity=DataQualitySeverity.MEDIUM,
                    message="Minimum academic requirement is missing.",
                )
            )
        structured_types = {rule.rule_type for rule in opportunity.eligibility_rules}
        if not structured_types:
            issues.append(
                self._issue(
                    opportunity,
                    source=best_source,
                    code="structured_eligibility_missing",
                    severity=DataQualitySeverity.HIGH,
                    message=(
                        "Public opportunity has no structured eligibility rules and requires "
                        "curator coverage."
                    ),
                )
            )
        unstructured_dependencies = {
            "nationality_eligibility": (
                opportunity.nationality_eligibility,
                {"nationality"},
            ),
            "field_eligibility": (opportunity.field_eligibility, {"field"}),
            "academic_requirement": (
                opportunity.minimum_academic_requirement,
                {"cgpa", "percentage", "current_education_level"},
            ),
            "english_test_requirement": (
                opportunity.english_language_requirement
                or opportunity.standardized_test_requirement,
                {"ielts", "toefl", "duolingo", "english_test_status"},
            ),
        }
        for dependency, (
            text,
            required_types,
        ) in unstructured_dependencies.items():
            has_structured_rule = any(
                rule_type.value in required_types for rule_type in structured_types
            )
            if text and not has_structured_rule:
                issues.append(
                    self._issue(
                        opportunity,
                        source=best_source,
                        code=f"unstructured_eligibility_{dependency}",
                        severity=DataQualitySeverity.HIGH,
                        message=(
                            "Public opportunity still depends on unstructured eligibility text: "
                            f"{dependency.replace('_', ' ')}."
                        ),
                    )
                )
        for rule in opportunity.eligibility_rules:
            source = rule.source
            excerpt = rule.source_excerpt
            if (
                source is None
                or source.opportunity_id != opportunity.id
                or source.source_type is not SourceType.OFFICIAL
                or excerpt is None
                or excerpt.source_id != source.id
            ):
                issues.append(
                    self._issue(
                        opportunity,
                        source=source,
                        code="eligibility_rule_evidence_missing",
                        severity=DataQualitySeverity.HIGH,
                        message=(
                            "Structured eligibility rule lacks a linked official source and "
                            "immutable excerpt."
                        ),
                    )
                )
        if opportunity.funding_type.value == "unknown":
            issues.append(
                self._issue(
                    opportunity,
                    source=best_source,
                    code="funding_type_unknown",
                    severity=DataQualitySeverity.MEDIUM,
                    message="Funding type is unknown.",
                )
            )
        if opportunity.data_confidence.value == "low":
            issues.append(
                self._issue(
                    opportunity,
                    source=best_source,
                    code="low_data_confidence",
                    severity=DataQualitySeverity.MEDIUM,
                    message="Data confidence is low.",
                )
            )
        return issues

    @staticmethod
    def _issue(
        opportunity: Opportunity,
        *,
        code: str,
        severity: DataQualitySeverity,
        message: str,
        source: Source | None = None,
    ) -> DataQualityIssueResponse:
        return DataQualityIssueResponse(
            code=code,
            severity=severity,
            message=message,
            opportunity_id=opportunity.id,
            opportunity_name=opportunity.name,
            source_id=source.id if source else None,
        )

    @staticmethod
    def _sorted_issues(
        issues: list[DataQualityIssueResponse] | object,
    ) -> list[DataQualityIssueResponse]:
        severity_rank = {
            DataQualitySeverity.HIGH: 0,
            DataQualitySeverity.MEDIUM: 1,
            DataQualitySeverity.LOW: 2,
        }
        return sorted(
            list(issues),
            key=lambda issue: (
                severity_rank[issue.severity],
                issue.opportunity_name,
                issue.code,
            ),
        )

    @staticmethod
    def _source_can_publish(source: Source) -> bool:
        return EvidencePolicy.source_can_publish(source)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _pagination(*, total: int, limit: int, offset: int, count: int) -> PaginationMeta:
        return PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            count=count,
            has_next=offset + count < total,
            has_previous=offset > 0,
        )
