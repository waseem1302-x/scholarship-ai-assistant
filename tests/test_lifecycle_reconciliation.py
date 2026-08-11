from datetime import UTC, datetime, timedelta

from app.cli.reconcile_opportunity_lifecycles import reconcile_opportunity_lifecycles
from app.modules.opportunities.models import (
    DegreeLevel,
    Opportunity,
    OpportunityStatus,
    Provider,
    Source,
    SourceType,
    VerificationStatus,
)


def test_reconciliation_expires_closed_records_without_deleting_them(db_session) -> None:
    provider = Provider(name="Lifecycle Provider")
    opportunity = Opportunity(
        provider=provider,
        name="Past application cycle",
        country="Malaysia",
        degree_level=DegreeLevel.MASTERS,
        application_deadline=datetime.now(UTC) - timedelta(days=1),
        status=OpportunityStatus.ACTIVE,
    )
    opportunity.sources.append(
        Source(
            url="https://example.edu/past-cycle",
            source_type=SourceType.OFFICIAL,
            title="Official past cycle source",
            relevant_excerpt="Official source confirms this application's deadline.",
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            last_verified_at=datetime.now(UTC),
        )
    )
    db_session.add(opportunity)
    db_session.commit()

    result = reconcile_opportunity_lifecycles(db_session)
    db_session.refresh(opportunity)

    assert result["expired"] == 1
    assert opportunity.status is OpportunityStatus.EXPIRED
    assert db_session.get(Opportunity, opportunity.id) is not None
