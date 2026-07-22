import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
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

    def list_admin_opportunities(self) -> list[Opportunity]:
        return list(
            self.session.scalars(
                select(Opportunity)
                .options(
                    joinedload(Opportunity.provider),
                    joinedload(Opportunity.university),
                    selectinload(Opportunity.sources),
                )
                .order_by(Opportunity.created_at.desc())
            )
        )

    def list_public_opportunities(
        self,
        *,
        country: str | None = None,
        degree_level: DegreeLevel | None = None,
        funding_type: FundingType | None = None,
        deadline_before: datetime | None = None,
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
        if deadline_before is not None:
            statement = statement.where(Opportunity.application_deadline <= deadline_before)

        return list(self.session.scalars(statement))
