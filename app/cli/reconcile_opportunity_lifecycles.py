"""Close past application cycles without deleting historical opportunity data."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.modules.opportunities.lifecycle import effective_application_window
from app.modules.opportunities.models import (
    ApplicationWindowState,
    Opportunity,
    OpportunityStatus,
)
from app.modules.opportunities.service import OpportunityService


def reconcile_opportunity_lifecycles(session: Session, *, dry_run: bool = False) -> dict[str, int]:
    opportunities = session.scalars(
        select(Opportunity).options(
            selectinload(Opportunity.sources),
            selectinload(Opportunity.cycles),
        )
    ).all()
    closed = 0
    for opportunity in opportunities:
        if opportunity.status is not OpportunityStatus.ACTIVE:
            continue
        source = OpportunityService._official_source(opportunity)
        window = effective_application_window(opportunity, source)
        if window.state is ApplicationWindowState.CLOSED:
            closed += 1
            if not dry_run:
                opportunity.status = OpportunityStatus.EXPIRED
    if not dry_run:
        session.commit()
    return {"checked": len(opportunities), "expired": closed, "dry_run": int(dry_run)}


def main() -> None:
    dry_run = os.getenv("APP_RECONCILE_DRY_RUN", "false").lower() == "true"
    with SessionLocal() as session:
        print(reconcile_opportunity_lifecycles(session, dry_run=dry_run))


if __name__ == "__main__":
    main()
