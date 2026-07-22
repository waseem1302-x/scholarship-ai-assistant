import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.opportunities.models import (
    DegreeLevel,
    FundingType,
    Opportunity,
    OpportunityStatus,
    Provider,
    Source,
    SourceType,
    University,
    VerificationStatus,
)


class OpportunityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_provider_by_name(self, name: str) -> Provider | None:
        return self.session.scalar(
            select(Provider).where(func.lower(Provider.name) == name.lower())
        )

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

    def get_or_create_provider(self, name: str, website_url: str | None) -> Provider:
        provider = self.get_provider_by_name(name)
        if provider is not None:
            if website_url and provider.website_url is None:
                provider.website_url = website_url
            return provider

        provider = Provider(name=name, website_url=website_url)
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
            )
        )

    def get_source(self, source_id: uuid.UUID) -> Source | None:
        return self.session.get(Source, source_id)

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
    ) -> list[Opportunity]:
        statement: Select[tuple[Opportunity]] = (
            select(Opportunity)
            .options(
                joinedload(Opportunity.provider),
                joinedload(Opportunity.university),
                selectinload(Opportunity.sources),
            )
            .order_by(Opportunity.created_at.desc())
        )
        if verification_status is not None or needs_review is not None:
            statement = statement.join(Source)
        if country is not None:
            statement = statement.where(func.lower(Opportunity.country) == country.lower())
        if degree_level is not None:
            statement = statement.where(Opportunity.degree_level == degree_level)
        if status is not None:
            statement = statement.where(Opportunity.status == status)
        if verification_status is not None:
            statement = statement.where(Source.verification_status == verification_status)
        if needs_review is True:
            statement = statement.where(
                or_(
                    Opportunity.status == OpportunityStatus.DRAFT,
                    Source.verification_status.in_(
                        [
                            VerificationStatus.UNVERIFIED,
                            VerificationStatus.NEEDS_REVIEW,
                            VerificationStatus.CONFLICTING_INFORMATION,
                        ]
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

        return list(self.session.scalars(statement.distinct()))

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
    ) -> list[Opportunity]:
        statement: Select[tuple[Opportunity]] = (
            select(Opportunity)
            .join(Source)
            .where(
                Opportunity.status == OpportunityStatus.ACTIVE,
                Source.source_type == SourceType.OFFICIAL,
                Source.verification_status == VerificationStatus.OFFICIALLY_VERIFIED,
            )
            .options(
                joinedload(Opportunity.provider),
                joinedload(Opportunity.university),
                selectinload(Opportunity.sources),
            )
            .order_by(Opportunity.application_deadline.asc().nulls_last(), Opportunity.name)
            .distinct()
        )
        if country is not None:
            statement = statement.where(func.lower(Opportunity.country) == country.lower())
        if degree_level is not None:
            statement = statement.where(Opportunity.degree_level == degree_level)
        if funding_type is not None:
            statement = statement.where(Opportunity.funding_type == funding_type)
        if field is not None:
            statement = statement.where(
                self._contains_case_insensitive(Opportunity.field_eligibility, field)
            )
        if nationality is not None:
            statement = statement.where(
                self._contains_case_insensitive(Opportunity.nationality_eligibility, nationality)
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
            statement = statement.where(
                self._contains_case_insensitive(Opportunity.application_fee_info, application_fee)
            )
        if english_requirement is not None:
            statement = statement.where(
                self._contains_case_insensitive(
                    Opportunity.english_language_requirement, english_requirement
                )
            )
        if verified_after is not None:
            statement = statement.where(Source.last_verified_at >= verified_after)

        return list(self.session.scalars(statement))

    @staticmethod
    def _contains_case_insensitive(column: object, value: str) -> object:
        return func.lower(column).contains(value.strip().lower())
