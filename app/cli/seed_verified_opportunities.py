import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.auth.models import User, UserRole
from app.modules.auth.repository import AuthRepository
from app.modules.opportunities.models import Source, VerificationRecord, VerificationStatus
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.schemas import OpportunityCreate, VerificationUpdate
from app.modules.opportunities.service import OpportunityService

DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "seed" / "verified_opportunities.json"
)


class SeedError(Exception):
    pass


def load_seed_payload(path: Path = DEFAULT_SEED_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as seed_file:
        payload = json.load(seed_file)
    if not isinstance(payload.get("records"), list):
        raise SeedError("Seed file must contain a records list")
    return payload


def find_seed_admin(session: Session, email: str | None = None) -> User:
    repository = AuthRepository(session)
    if email:
        user = repository.get_user_by_email(email.strip().lower())
        if user is None:
            raise SeedError(f"No admin user found for {email}")
        if user.role is not UserRole.ADMIN:
            raise SeedError(f"User {email} is not an admin")
        return user

    admin = (
        session.query(User).filter(User.role == UserRole.ADMIN).order_by(User.created_at).first()
    )
    if admin is None:
        raise SeedError("Create an admin user before loading verified seed opportunities")
    return admin


def seed_verified_opportunities(
    session: Session,
    *,
    admin_email: str | None = None,
    seed_path: Path = DEFAULT_SEED_PATH,
    dry_run: bool = False,
) -> dict[str, int]:
    seed_payload = load_seed_payload(seed_path)
    admin = None if dry_run else find_seed_admin(session, admin_email)
    opportunity_service = OpportunityService(session)
    opportunity_repository = OpportunityRepository(session)
    summary = {"created": 0, "skipped_duplicates": 0, "validated": 0}

    for raw_record in seed_payload["records"]:
        record = dict(raw_record)
        additional_sources = record.pop("additional_sources", [])
        opportunity_payload = OpportunityCreate.model_validate(record)
        summary["validated"] += 1

        duplicate = opportunity_repository.find_duplicate_opportunity(
            provider_name=opportunity_payload.provider_name,
            name=opportunity_payload.name,
            country=opportunity_payload.country,
            intake_year=opportunity_payload.intake_year,
        )
        if duplicate is not None:
            summary["skipped_duplicates"] += 1
            continue

        if dry_run:
            continue

        if admin is None:
            raise SeedError("Create an admin user before loading verified seed opportunities")

        created = opportunity_service.create_opportunity(opportunity_payload, created_by=admin)
        verified = opportunity_service.verify_source(
            created.id,
            VerificationUpdate(verification_status=VerificationStatus.OFFICIALLY_VERIFIED),
            checked_by=admin,
        )
        opportunity = opportunity_repository.get_opportunity(verified.id)
        if opportunity is None:
            raise SeedError(f"Created opportunity {verified.id} could not be reloaded")

        checked_at = datetime.now(UTC)
        for additional_source in additional_sources:
            source = Source(
                opportunity_id=opportunity.id,
                url=additional_source["url"],
                source_type=additional_source.get("source_type", "official"),
                title=additional_source["title"],
                relevant_excerpt=additional_source["relevant_excerpt"],
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
                verified_by_user_id=admin.id,
                last_verified_at=checked_at,
            )
            session.add(source)
            session.flush()
            session.add(
                VerificationRecord(
                    opportunity_id=opportunity.id,
                    source_id=source.id,
                    status=VerificationStatus.OFFICIALLY_VERIFIED,
                    checked_by_user_id=admin.id,
                    notes="Verified seed dataset source",
                )
            )

        session.commit()
        summary["created"] += 1

    return summary


def main() -> None:
    seed_path = Path(os.getenv("APP_SEED_FILE", DEFAULT_SEED_PATH))
    admin_email = os.getenv("APP_SEED_ADMIN_EMAIL")
    dry_run = os.getenv("APP_SEED_DRY_RUN", "false").lower() in {"1", "true", "yes"}

    with SessionLocal() as session:
        summary = seed_verified_opportunities(
            session,
            admin_email=admin_email,
            seed_path=seed_path,
            dry_run=dry_run,
        )
    mode = "validated" if dry_run else "loaded"
    print(
        f"Verified seed opportunities {mode}: "
        f"{summary['validated']} validated, "
        f"{summary['created']} created, "
        f"{summary['skipped_duplicates']} duplicates skipped"
    )


if __name__ == "__main__":
    main()
