import re
import uuid
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import (
    Select,
    String,
    and_,
    case,
    cast,
    false,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.lifecycle import SOURCE_FRESHNESS_DAYS
from app.modules.opportunities.models import (
    ApplicationFeeStatus,
    ApplicationWindowState,
    DataConfidence,
    DegreeLevel,
    DuplicateSuggestion,
    DuplicateSuggestionStatus,
    EligibilityOperator,
    EligibilityRule,
    EligibilityRuleType,
    EligibilityRuleValue,
    FundingType,
    Opportunity,
    OpportunityStatus,
    Provider,
    Source,
    SourceExcerpt,
    SourceType,
    University,
    VerificationStatus,
)

NATIONALITY_BROAD_VALUE_KEYS = {
    "all-countries",
    "all-nationalities",
    "any-nationality",
    "citizens-of-all-countries",
    "foreign-citizens",
    "foreign-students",
    "international",
    "international-applicants",
    "international-students",
}
FIELD_BROAD_VALUE_KEYS = {
    "all-disciplines",
    "all-fields",
    "any-discipline",
    "any-field",
    "any-programme",
    "any-program",
}
APPLICATION_FEE_ALIASES = {
    "free": ApplicationFeeStatus.NOT_REQUIRED,
    "none": ApplicationFeeStatus.NOT_REQUIRED,
    "no": ApplicationFeeStatus.NOT_REQUIRED,
    "no-application-fee": ApplicationFeeStatus.NOT_REQUIRED,
    "no-fee": ApplicationFeeStatus.NOT_REQUIRED,
    "not-required": ApplicationFeeStatus.NOT_REQUIRED,
    "required": ApplicationFeeStatus.REQUIRED,
    "fee-required": ApplicationFeeStatus.REQUIRED,
    "waiver": ApplicationFeeStatus.WAIVER_AVAILABLE,
    "waiver-available": ApplicationFeeStatus.WAIVER_AVAILABLE,
    "fee-waiver": ApplicationFeeStatus.WAIVER_AVAILABLE,
    "unknown": ApplicationFeeStatus.UNKNOWN,
}
ENGLISH_TEST_TYPE_KEYS = {
    "duolingo": EligibilityRuleType.DUOLINGO,
    "gre": EligibilityRuleType.GRE,
    "ielts": EligibilityRuleType.IELTS,
    "toefl": EligibilityRuleType.TOEFL,
}
ENGLISH_RULE_TYPES = {
    EligibilityRuleType.DUOLINGO,
    EligibilityRuleType.ENGLISH_TEST_STATUS,
    EligibilityRuleType.GRE,
    EligibilityRuleType.GRE_STATUS,
    EligibilityRuleType.IELTS,
    EligibilityRuleType.TOEFL,
}


class OpportunityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_provider_by_name(self, name: str) -> Provider | None:
        return self.session.scalar(
            select(Provider).where(func.lower(Provider.name) == name.lower())
        )

    def get_provider_by_canonical_id(self, canonical_id: str) -> Provider | None:
        return self.session.scalar(select(Provider).where(Provider.canonical_id == canonical_id))

    def find_duplicate_opportunity(
        self,
        *,
        provider_name: str,
        name: str,
        country: str,
        intake_year: int | None,
    ) -> Opportunity | None:
        return self.session.scalar(
            select(Opportunity)
            .join(Provider)
            .where(
                func.lower(Provider.name) == provider_name.lower(),
                func.lower(Opportunity.name) == name.lower(),
                func.lower(Opportunity.country) == country.lower(),
                Opportunity.intake_year == intake_year,
            )
        )

    def find_duplicate_by_canonical_identity(
        self,
        *,
        provider_id: uuid.UUID,
        programme_family_id: str,
        cycle_id: str | None,
        degree_level: DegreeLevel,
        funding_type: FundingType,
    ) -> Opportunity | None:
        return self.session.scalar(
            select(Opportunity).where(
                Opportunity.provider_id == provider_id,
                Opportunity.programme_family_id == programme_family_id,
                Opportunity.cycle_id == cycle_id,
                Opportunity.degree_level == degree_level,
                Opportunity.funding_type == funding_type,
            )
        )

    def get_or_create_provider(
        self, name: str, website_url: str | None, canonical_id: str
    ) -> Provider:
        provider = self.get_provider_by_canonical_id(canonical_id) or self.get_provider_by_name(
            name
        )
        if provider is not None:
            if website_url and provider.website_url is None:
                provider.website_url = website_url
            if not provider.canonical_id:
                provider.canonical_id = canonical_id
            return provider

        provider = Provider(name=name, website_url=website_url, canonical_id=canonical_id)
        self.session.add(provider)
        self.session.flush()
        return provider

    def get_or_create_university(
        self, name: str | None, country: str, website_url: str | None
    ) -> University | None:
        if name is None:
            return None

        university = self.session.scalar(
            select(University).where(
                func.lower(University.name) == name.lower(),
                func.lower(University.country) == country.lower(),
            )
        )
        if university is not None:
            if website_url and university.website_url is None:
                university.website_url = website_url
            return university

        university = University(name=name, country=country, website_url=website_url)
        self.session.add(university)
        self.session.flush()
        return university

    def add_opportunity(self, opportunity: Opportunity) -> None:
        self.session.add(opportunity)

    def get_opportunity(self, opportunity_id: uuid.UUID) -> Opportunity | None:
        return self.session.scalar(
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .options(
                joinedload(Opportunity.provider),
                joinedload(Opportunity.university),
                selectinload(Opportunity.sources),
                selectinload(Opportunity.cycles),
                selectinload(Opportunity.eligibility_rules),
            )
        )

    def get_source(self, source_id: uuid.UUID) -> Source | None:
        return self.session.get(Source, source_id)

    def find_opportunities_by_canonical_url(self, canonical_url: str) -> list[Opportunity]:
        statement = (
            select(Opportunity)
            .join(Source)
            .where(Source.canonical_url == canonical_url)
            .options(joinedload(Opportunity.provider), selectinload(Opportunity.sources))
        )
        return list(self.session.scalars(statement))

    def create_duplicate_suggestions(self, opportunity: Opportunity) -> None:
        existing_ids = {
            suggestion.matched_opportunity_id for suggestion in opportunity.duplicate_suggestions
        }
        canonical_urls = {
            source.canonical_url for source in opportunity.sources if source.canonical_url
        }
        candidates = self.session.scalars(
            select(Opportunity)
            .where(
                Opportunity.id != opportunity.id,
                or_(
                    and_(
                        Opportunity.provider_id == opportunity.provider_id,
                        Opportunity.country == opportunity.country,
                    ),
                    Opportunity.sources.any(Source.canonical_url.in_(canonical_urls)),
                ),
            )
            .options(joinedload(Opportunity.provider), selectinload(Opportunity.sources))
        )
        for candidate in candidates:
            if candidate.id in existing_ids:
                continue
            candidate_urls = {
                source.canonical_url for source in candidate.sources if source.canonical_url
            }
            score = max(
                SequenceMatcher(
                    None, opportunity.name.casefold(), candidate.name.casefold()
                ).ratio(),
                0.95 if canonical_urls & candidate_urls else 0.0,
            )
            if score >= 0.80:
                self.session.add(
                    DuplicateSuggestion(
                        opportunity_id=opportunity.id,
                        matched_opportunity_id=candidate.id,
                        score=score,
                    )
                )

    def list_duplicate_suggestions(self, *, limit: int, offset: int) -> list[DuplicateSuggestion]:
        statement = (
            select(DuplicateSuggestion)
            .where(DuplicateSuggestion.status == DuplicateSuggestionStatus.PENDING)
            .options(
                joinedload(DuplicateSuggestion.opportunity),
                joinedload(DuplicateSuggestion.matched_opportunity),
            )
            .order_by(DuplicateSuggestion.score.desc(), DuplicateSuggestion.created_at)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def count_duplicate_suggestions(self) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(DuplicateSuggestion)
                .where(DuplicateSuggestion.status == DuplicateSuggestionStatus.PENDING)
            )
            or 0
        )

    def get_duplicate_suggestion(self, suggestion_id: uuid.UUID) -> DuplicateSuggestion | None:
        return self.session.scalar(
            select(DuplicateSuggestion)
            .where(DuplicateSuggestion.id == suggestion_id)
            .options(
                joinedload(DuplicateSuggestion.opportunity),
                joinedload(DuplicateSuggestion.matched_opportunity),
            )
        )

    @staticmethod
    def canonicalize_url(url: str) -> str:
        parsed = urlsplit(url.strip())
        query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        path = parsed.path.rstrip("/") or "/"
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))

    def list_sources_due_for_monitoring(
        self,
        *,
        now: datetime,
        check_interval_days: int,
        freshness_days: int,
        limit: int,
    ) -> list[Source]:
        check_cutoff = now - timedelta(days=check_interval_days)
        freshness_cutoff = now - timedelta(days=freshness_days)
        statement = (
            select(Source)
            .join(Opportunity)
            .where(
                Opportunity.status == OpportunityStatus.ACTIVE,
                Source.source_type == SourceType.OFFICIAL,
                Source.verification_status == VerificationStatus.OFFICIALLY_VERIFIED,
                or_(
                    Source.last_updated_at.is_(None),
                    Source.last_updated_at <= check_cutoff,
                    Source.last_verified_at <= freshness_cutoff,
                ),
            )
            .order_by(
                Source.last_updated_at.asc().nulls_first(),
                Source.date_collected.asc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def list_admin_opportunities(
        self,
        *,
        country: str | None = None,
        degree_level: DegreeLevel | None = None,
        status: OpportunityStatus | None = None,
        verification_status: VerificationStatus | None = None,
        needs_review: bool | None = None,
        provider_query: str | None = None,
        search_query: str | None = None,
        deadline_after: datetime | None = None,
        deadline_before: datetime | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Opportunity]:
        statement = self._admin_opportunities_statement(
            country=country,
            degree_level=degree_level,
            status=status,
            verification_status=verification_status,
            needs_review=needs_review,
            provider_query=provider_query,
            search_query=search_query,
            deadline_after=deadline_after,
            deadline_before=deadline_before,
        ).order_by(Opportunity.created_at.desc())
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        return list(self.session.scalars(statement))

    def count_admin_opportunities(
        self,
        *,
        country: str | None = None,
        degree_level: DegreeLevel | None = None,
        status: OpportunityStatus | None = None,
        verification_status: VerificationStatus | None = None,
        needs_review: bool | None = None,
        provider_query: str | None = None,
        search_query: str | None = None,
        deadline_after: datetime | None = None,
        deadline_before: datetime | None = None,
    ) -> int:
        statement = self._admin_opportunities_statement(
            country=country,
            degree_level=degree_level,
            status=status,
            verification_status=verification_status,
            needs_review=needs_review,
            provider_query=provider_query,
            search_query=search_query,
            deadline_after=deadline_after,
            deadline_before=deadline_before,
        )
        return self._count_statement(statement)

    def list_data_quality_issues(self, *, limit: int, offset: int) -> list[dict[str, object]]:
        issues = self._data_quality_issues_statement().subquery()
        severity_rank = case(
            (issues.c.severity == "high", 0),
            (issues.c.severity == "medium", 1),
            else_=2,
        )
        statement = (
            select(issues)
            .order_by(severity_rank, issues.c.opportunity_name, issues.c.code)
            .offset(offset)
            .limit(limit)
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def count_data_quality_issues(self) -> int:
        return (
            self.session.scalar(
                select(func.count()).select_from(self._data_quality_issues_statement().subquery())
            )
            or 0
        )

    def list_data_quality_issues_for_opportunities(
        self, opportunity_ids: list[uuid.UUID]
    ) -> list[dict[str, object]]:
        if not opportunity_ids:
            return []
        issues = self._data_quality_issues_statement().subquery()
        severity_rank = case(
            (issues.c.severity == "high", 0),
            (issues.c.severity == "medium", 1),
            else_=2,
        )
        statement = (
            select(issues)
            .where(issues.c.opportunity_id.in_(opportunity_ids))
            .order_by(severity_rank, issues.c.opportunity_name, issues.c.code)
        )
        return [dict(row) for row in self.session.execute(statement).mappings()]

    def list_review_queue_opportunities(self, *, limit: int, offset: int) -> list[Opportunity]:
        issue_rows = self._data_quality_issues_statement().subquery()
        candidate_ids = select(issue_rows.c.opportunity_id).where(
            issue_rows.c.severity.in_(["high", "medium"])
        )
        statement = (
            select(Opportunity)
            .where(Opportunity.id.in_(candidate_ids))
            .options(
                joinedload(Opportunity.provider),
                joinedload(Opportunity.university),
                selectinload(Opportunity.sources),
                selectinload(Opportunity.cycles),
                selectinload(Opportunity.eligibility_rules),
            )
            .order_by(Opportunity.name)
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def count_review_queue_opportunities(self) -> int:
        issue_rows = self._data_quality_issues_statement().subquery()
        candidate_ids = select(issue_rows.c.opportunity_id).where(
            issue_rows.c.severity.in_(["high", "medium"])
        )
        return (
            self.session.scalar(
                select(func.count()).select_from(
                    select(Opportunity.id).where(Opportunity.id.in_(candidate_ids)).subquery()
                )
            )
            or 0
        )

    @staticmethod
    def _data_quality_issues_statement() -> Select[tuple[object, ...]]:
        """Return one database row per quality issue, ready for SQL pagination."""
        now = datetime.now(UTC)
        stale_before = now - timedelta(days=SOURCE_FRESHNESS_DAYS)
        best_source_id = (
            select(Source.id)
            .where(Source.opportunity_id == Opportunity.id)
            .order_by(
                case(
                    (
                        and_(
                            Source.source_type == SourceType.OFFICIAL,
                            Source.verification_status == VerificationStatus.OFFICIALLY_VERIFIED,
                        ),
                        0,
                    ),
                    else_=1,
                ),
                Source.date_collected,
            )
            .limit(1)
            .scalar_subquery()
        )

        def issue(
            code: str,
            severity: str,
            message: str,
            condition: object,
            *,
            source_id: object | None = None,
        ) -> Select[tuple[object, ...]]:
            return select(
                literal(code).label("code"),
                literal(severity).label("severity"),
                literal(message).label("message"),
                Opportunity.id.label("opportunity_id"),
                Opportunity.name.label("opportunity_name"),
                (source_id if source_id is not None else best_source_id).label("source_id"),
            ).where(condition)

        source_requires_review = issue(
            "source_requires_review",
            "high",
            "Source is not verified and requires curator review.",
            Source.verification_status.in_(
                [VerificationStatus.UNVERIFIED, VerificationStatus.NEEDS_REVIEW]
            ),
            source_id=Source.id,
        ).join(Source, Source.opportunity_id == Opportunity.id)
        source_conflict = issue(
            "source_conflict",
            "high",
            "Source has conflicting information that must be resolved.",
            Source.verification_status == VerificationStatus.CONFLICTING_INFORMATION,
            source_id=Source.id,
        ).join(Source, Source.opportunity_id == Opportunity.id)
        source_never_verified = issue(
            "source_never_verified",
            "medium",
            "Source has no recorded verification timestamp.",
            Source.last_verified_at.is_(None),
            source_id=Source.id,
        ).join(Source, Source.opportunity_id == Opportunity.id)
        source_stale = issue(
            "source_stale",
            "high",
            f"Source has not been reverified within {SOURCE_FRESHNESS_DAYS} days.",
            Source.last_verified_at < stale_before,
            source_id=Source.id,
        ).join(Source, Source.opportunity_id == Opportunity.id)
        source_hash_missing = issue(
            "source_hash_missing",
            "low",
            "Source has no stored content hash for change monitoring.",
            Source.content_hash.is_(None),
            source_id=Source.id,
        ).join(Source, Source.opportunity_id == Opportunity.id)
        missing_sources = issue(
            "official_source_missing",
            "high",
            "Opportunity has no source evidence attached.",
            ~Opportunity.sources.any(),
        )
        missing_deadline = issue(
            "deadline_missing",
            "high",
            "Application deadline is missing or unknown.",
            Opportunity.application_deadline.is_(None),
        )
        missing_documents = issue(
            "required_documents_missing",
            "medium",
            "Required documents are not structured.",
            cast(Opportunity.required_documents, String) == "[]",
        )
        missing_english = issue(
            "english_requirement_missing",
            "medium",
            "English-language requirement is missing.",
            Opportunity.english_language_requirement.is_(None),
        )
        missing_academic = issue(
            "academic_requirement_missing",
            "medium",
            "Minimum academic requirement is missing.",
            Opportunity.minimum_academic_requirement.is_(None),
        )
        missing_rules = issue(
            "structured_eligibility_missing",
            "high",
            "Public opportunity has no structured eligibility rules and requires curator coverage.",
            ~Opportunity.eligibility_rules.any(),
        )

        def missing_rule_types(*types: EligibilityRuleType) -> object:
            return ~Opportunity.eligibility_rules.any(EligibilityRule.rule_type.in_(types))

        unstructured_nationality = issue(
            "unstructured_eligibility_nationality_eligibility",
            "high",
            "Public opportunity still depends on unstructured eligibility text: "
            "nationality eligibility.",
            and_(
                Opportunity.nationality_eligibility.is_not(None),
                missing_rule_types(EligibilityRuleType.NATIONALITY),
            ),
        )
        unstructured_field = issue(
            "unstructured_eligibility_field_eligibility",
            "high",
            "Public opportunity still depends on unstructured eligibility text: field eligibility.",
            and_(
                Opportunity.field_eligibility.is_not(None),
                missing_rule_types(EligibilityRuleType.FIELD),
            ),
        )
        unstructured_academic = issue(
            "unstructured_eligibility_academic_requirement",
            "high",
            "Public opportunity still depends on unstructured eligibility text: "
            "academic requirement.",
            and_(
                Opportunity.minimum_academic_requirement.is_not(None),
                missing_rule_types(
                    EligibilityRuleType.CGPA,
                    EligibilityRuleType.PERCENTAGE,
                    EligibilityRuleType.CURRENT_EDUCATION_LEVEL,
                ),
            ),
        )
        unstructured_english = issue(
            "unstructured_eligibility_english_test_requirement",
            "high",
            "Public opportunity still depends on unstructured eligibility text: "
            "english test requirement.",
            and_(
                or_(
                    Opportunity.english_language_requirement.is_not(None),
                    Opportunity.standardized_test_requirement.is_not(None),
                ),
                missing_rule_types(
                    EligibilityRuleType.IELTS,
                    EligibilityRuleType.TOEFL,
                    EligibilityRuleType.DUOLINGO,
                    EligibilityRuleType.ENGLISH_TEST_STATUS,
                ),
            ),
        )
        broken_evidence = issue(
            "eligibility_rule_evidence_missing",
            "high",
            "Structured eligibility rule lacks a linked official source and immutable excerpt.",
            or_(
                EligibilityRule.source_id.is_(None),
                EligibilityRule.source_excerpt_id.is_(None),
                ~EligibilityRule.source.has(
                    and_(
                        Source.opportunity_id == Opportunity.id,
                        Source.source_type == SourceType.OFFICIAL,
                    )
                ),
                ~EligibilityRule.source_excerpt.has(
                    SourceExcerpt.source_id == EligibilityRule.source_id
                ),
            ),
            source_id=EligibilityRule.source_id,
        ).join(EligibilityRule, EligibilityRule.opportunity_id == Opportunity.id)
        funding_unknown = issue(
            "funding_type_unknown",
            "medium",
            "Funding type is unknown.",
            Opportunity.funding_type == FundingType.UNKNOWN,
        )
        low_confidence = issue(
            "low_data_confidence",
            "medium",
            "Data confidence is low.",
            Opportunity.data_confidence == DataConfidence.LOW,
        )
        return union_all(
            source_requires_review,
            source_conflict,
            source_never_verified,
            source_stale,
            source_hash_missing,
            missing_sources,
            missing_deadline,
            missing_documents,
            missing_english,
            missing_academic,
            missing_rules,
            unstructured_nationality,
            unstructured_field,
            unstructured_academic,
            unstructured_english,
            broken_evidence,
            funding_unknown,
            low_confidence,
        )

    def _admin_opportunities_statement(
        self,
        *,
        country: str | None = None,
        degree_level: DegreeLevel | None = None,
        status: OpportunityStatus | None = None,
        verification_status: VerificationStatus | None = None,
        needs_review: bool | None = None,
        provider_query: str | None = None,
        search_query: str | None = None,
        deadline_after: datetime | None = None,
        deadline_before: datetime | None = None,
    ) -> Select[tuple[Opportunity]]:
        statement: Select[tuple[Opportunity]] = select(Opportunity).options(
            joinedload(Opportunity.provider),
            joinedload(Opportunity.university),
            selectinload(Opportunity.sources),
            selectinload(Opportunity.cycles),
            selectinload(Opportunity.eligibility_rules),
        )
        if country is not None:
            statement = statement.where(func.lower(Opportunity.country) == country.lower())
        if degree_level is not None:
            statement = statement.where(Opportunity.degree_level == degree_level)
        if status is not None:
            statement = statement.where(Opportunity.status == status)
        if verification_status is not None:
            statement = statement.where(
                Opportunity.sources.any(Source.verification_status == verification_status)
            )
        if needs_review is True:
            statement = statement.where(
                or_(
                    Opportunity.status == OpportunityStatus.DRAFT,
                    Opportunity.sources.any(
                        Source.verification_status.in_(
                            [
                                VerificationStatus.UNVERIFIED,
                                VerificationStatus.NEEDS_REVIEW,
                                VerificationStatus.CONFLICTING_INFORMATION,
                            ]
                        )
                    ),
                )
            )
        if provider_query is not None:
            statement = statement.join(Provider).where(
                self._contains_case_insensitive(Provider.name, provider_query)
            )
        if search_query is not None:
            statement = statement.where(
                or_(
                    self._contains_case_insensitive(Opportunity.name, search_query),
                    self._contains_case_insensitive(Opportunity.field_eligibility, search_query),
                    self._contains_case_insensitive(
                        Opportunity.nationality_eligibility, search_query
                    ),
                    self._contains_case_insensitive(Opportunity.notes, search_query),
                )
            )
        if deadline_after is not None:
            statement = statement.where(Opportunity.application_deadline >= deadline_after)
        if deadline_before is not None:
            statement = statement.where(Opportunity.application_deadline <= deadline_before)

        return statement

    def list_public_opportunities(
        self,
        *,
        country: str | None = None,
        degree_level: DegreeLevel | None = None,
        funding_type: FundingType | None = None,
        field: str | None = None,
        nationality: str | None = None,
        intake_year: int | None = None,
        deadline_after: datetime | None = None,
        deadline_before: datetime | None = None,
        funding_coverage: str | None = None,
        application_fee: str | None = None,
        english_requirement: str | None = None,
        verified_after: datetime | None = None,
        open_now: bool = False,
        application_window_state: ApplicationWindowState | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Opportunity]:
        statement = self._public_opportunities_statement(
            country=country,
            degree_level=degree_level,
            funding_type=funding_type,
            field=field,
            nationality=nationality,
            intake_year=intake_year,
            deadline_after=deadline_after,
            deadline_before=deadline_before,
            funding_coverage=funding_coverage,
            application_fee=application_fee,
            english_requirement=english_requirement,
            verified_after=verified_after,
            open_now=open_now,
            application_window_state=application_window_state,
        ).order_by(*self._catalogue_order_by())
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        return list(self.session.scalars(statement))

    def count_public_opportunities(
        self,
        *,
        country: str | None = None,
        degree_level: DegreeLevel | None = None,
        funding_type: FundingType | None = None,
        field: str | None = None,
        nationality: str | None = None,
        intake_year: int | None = None,
        deadline_after: datetime | None = None,
        deadline_before: datetime | None = None,
        funding_coverage: str | None = None,
        application_fee: str | None = None,
        english_requirement: str | None = None,
        verified_after: datetime | None = None,
        open_now: bool = False,
        application_window_state: ApplicationWindowState | None = None,
    ) -> int:
        statement = self._public_opportunities_statement(
            country=country,
            degree_level=degree_level,
            funding_type=funding_type,
            field=field,
            nationality=nationality,
            intake_year=intake_year,
            deadline_after=deadline_after,
            deadline_before=deadline_before,
            funding_coverage=funding_coverage,
            application_fee=application_fee,
            english_requirement=english_requirement,
            verified_after=verified_after,
            open_now=open_now,
            application_window_state=application_window_state,
        )
        return self._count_statement(statement)

    def _public_opportunities_statement(
        self,
        *,
        country: str | None = None,
        degree_level: DegreeLevel | None = None,
        funding_type: FundingType | None = None,
        field: str | None = None,
        nationality: str | None = None,
        intake_year: int | None = None,
        deadline_after: datetime | None = None,
        deadline_before: datetime | None = None,
        funding_coverage: str | None = None,
        application_fee: str | None = None,
        english_requirement: str | None = None,
        verified_after: datetime | None = None,
        open_now: bool = False,
        application_window_state: ApplicationWindowState | None = None,
    ) -> Select[tuple[Opportunity]]:
        official_source_filters = [
            Source.source_type == SourceType.OFFICIAL,
            Source.verification_status == VerificationStatus.OFFICIALLY_VERIFIED,
        ]
        if verified_after is not None:
            official_source_filters.append(Source.last_verified_at >= verified_after)

        statement: Select[tuple[Opportunity]] = (
            select(Opportunity)
            .where(
                Opportunity.status == OpportunityStatus.ACTIVE,
                Opportunity.sources.any(and_(*official_source_filters)),
                ~Opportunity.sources.any(
                    and_(
                        Source.source_type == SourceType.OFFICIAL,
                        Source.verification_status.in_(
                            EvidencePolicy.DISQUALIFYING_OFFICIAL_STATUSES
                        ),
                    )
                ),
            )
            .options(
                joinedload(Opportunity.provider),
                joinedload(Opportunity.university),
                selectinload(Opportunity.sources),
                selectinload(Opportunity.cycles),
                selectinload(Opportunity.eligibility_rules),
            )
        )
        if country is not None:
            statement = statement.where(func.lower(Opportunity.country) == country.lower())
        if degree_level is not None:
            statement = statement.where(Opportunity.degree_level == degree_level)
        if funding_type is not None:
            statement = statement.where(Opportunity.funding_type == funding_type)
        if field is not None:
            statement = statement.where(
                self._structured_eligibility_filter(
                    EligibilityRuleType.FIELD,
                    field,
                    broad_value_keys=FIELD_BROAD_VALUE_KEYS,
                )
            )
        if nationality is not None:
            statement = statement.where(
                self._structured_eligibility_filter(
                    EligibilityRuleType.NATIONALITY,
                    nationality,
                    broad_value_keys=NATIONALITY_BROAD_VALUE_KEYS,
                )
            )
        if intake_year is not None:
            statement = statement.where(Opportunity.intake_year == intake_year)
        if deadline_after is not None:
            statement = statement.where(Opportunity.application_deadline >= deadline_after)
        if deadline_before is not None:
            statement = statement.where(Opportunity.application_deadline <= deadline_before)
        if funding_coverage is not None:
            statement = statement.where(
                or_(
                    self._contains_case_insensitive(Opportunity.tuition_coverage, funding_coverage),
                    self._contains_case_insensitive(
                        Opportunity.accommodation_coverage, funding_coverage
                    ),
                    self._contains_case_insensitive(Opportunity.travel_allowance, funding_coverage),
                    self._contains_case_insensitive(Opportunity.health_insurance, funding_coverage),
                )
            )
        if application_fee is not None:
            statement = statement.where(self._application_fee_filter(application_fee))
        if english_requirement is not None:
            statement = statement.where(self._english_requirement_filter(english_requirement))
        now = datetime.now(UTC)
        window_state = self._catalogue_window_state(now)
        if open_now:
            statement = statement.where(
                Opportunity.catalogue_cycle_is_archived.is_(False),
                or_(
                    Opportunity.catalogue_is_rolling.is_(True),
                    Opportunity.catalogue_application_deadline.is_not(None),
                ),
                or_(
                    Opportunity.catalogue_application_opening_date.is_(None),
                    Opportunity.catalogue_application_opening_date <= now,
                ),
                or_(
                    Opportunity.catalogue_application_deadline.is_(None),
                    Opportunity.catalogue_application_deadline >= now,
                ),
                Opportunity.sources.any(
                    and_(
                        Source.source_type == SourceType.OFFICIAL,
                        Source.verification_status == VerificationStatus.OFFICIALLY_VERIFIED,
                        Source.last_verified_at >= now - timedelta(days=SOURCE_FRESHNESS_DAYS),
                    )
                ),
            )
        elif application_window_state is not None:
            statement = statement.where(window_state == application_window_state)
        return statement

    @staticmethod
    def _catalogue_window_state(now: datetime) -> object:
        return case(
            (Opportunity.catalogue_cycle_is_archived.is_(True), ApplicationWindowState.ARCHIVED),
            (Opportunity.catalogue_application_deadline < now, ApplicationWindowState.CLOSED),
            (Opportunity.catalogue_application_opening_date > now, ApplicationWindowState.UPCOMING),
            (Opportunity.catalogue_is_rolling.is_(True), ApplicationWindowState.ROLLING),
            (
                Opportunity.catalogue_application_deadline.is_(None),
                ApplicationWindowState.DEADLINE_UNKNOWN,
            ),
            else_=ApplicationWindowState.OPEN,
        )

    @staticmethod
    def _catalogue_order_by() -> tuple[object, object, object]:
        now = datetime.now(UTC)
        window_state = OpportunityRepository._catalogue_window_state(now)
        priority = case(
            (window_state.in_([ApplicationWindowState.OPEN, ApplicationWindowState.ROLLING]), 0),
            (window_state == ApplicationWindowState.UPCOMING, 1),
            (window_state == ApplicationWindowState.DEADLINE_UNKNOWN, 2),
            (window_state == ApplicationWindowState.CLOSED, 3),
            else_=4,
        )
        return (
            priority,
            Opportunity.catalogue_application_deadline.asc().nulls_last(),
            Opportunity.name,
        )

    def _count_statement(self, statement: Select[tuple[Opportunity]]) -> int:
        count_statement = select(func.count()).select_from(
            statement.with_only_columns(Opportunity.id).order_by(None).distinct().subquery()
        )
        return self.session.scalar(count_statement) or 0

    def _structured_eligibility_filter(
        self,
        rule_type: EligibilityRuleType,
        raw_value: str,
        *,
        broad_value_keys: set[str],
    ) -> object:
        value_key = self.structured_value_key(raw_value)
        if not value_key:
            return false()

        include_keys = sorted({value_key, *broad_value_keys})
        has_including_rule = Opportunity.eligibility_rules.any(
            and_(
                EligibilityRule.rule_type == rule_type,
                EligibilityRule.operator.in_(
                    [EligibilityOperator.EQUALS, EligibilityOperator.IN]
                ),
                EligibilityRule.value_keys.any(EligibilityRuleValue.value_key.in_(include_keys)),
            )
        )
        has_excluding_rule = Opportunity.eligibility_rules.any(
            and_(
                EligibilityRule.rule_type == rule_type,
                EligibilityRule.operator == EligibilityOperator.NOT_IN,
                EligibilityRule.value_keys.any(EligibilityRuleValue.value_key == value_key),
            )
        )
        return and_(has_including_rule, ~has_excluding_rule)

    def _application_fee_filter(self, raw_value: str) -> object:
        status = APPLICATION_FEE_ALIASES.get(self.structured_value_key(raw_value))
        if status is None:
            return false()
        return Opportunity.application_fee_status == status

    def _english_requirement_filter(self, raw_value: str) -> object:
        value_key = self.structured_value_key(raw_value)
        if not value_key:
            return false()
        test_type = ENGLISH_TEST_TYPE_KEYS.get(value_key)
        if test_type is not None:
            return Opportunity.eligibility_rules.any(EligibilityRule.rule_type == test_type)
        return Opportunity.eligibility_rules.any(
            and_(
                EligibilityRule.rule_type.in_(ENGLISH_RULE_TYPES),
                EligibilityRule.value_keys.any(EligibilityRuleValue.value_key == value_key),
            )
        )

    @staticmethod
    def structured_value_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:120]

    @staticmethod
    def _contains_case_insensitive(column: object, value: str) -> object:
        return func.lower(column).contains(value.strip().lower())
