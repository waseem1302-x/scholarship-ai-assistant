import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.cli.bootstrap_demo import bootstrap_demo
from app.cli.seed_verified_opportunities import (
    DEFAULT_SEED_PATH,
    DEFAULT_SEED_PATHS,
    SeedError,
    load_seed_payload,
    load_seed_records,
    seed_verified_opportunities,
)
from app.core.security import hash_password
from app.modules.auth.models import User, UserRole
from app.modules.opportunities.models import Opportunity, OpportunityStatus, VerificationStatus
from app.modules.opportunities.schemas import OpportunityCreate

PASSWORD = "SeedPassword123"


def create_admin(db_session: Session, *, email: str = "seed-admin@example.com") -> User:
    admin = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(PASSWORD),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def test_verified_seed_file_contains_valid_opportunity_records() -> None:
    payload = load_seed_payload(DEFAULT_SEED_PATH)
    records = load_seed_records()

    assert payload["dataset_version"] == "2026-07-22"
    assert len(DEFAULT_SEED_PATHS) == 3
    assert len(records) == 50
    assert len(
        {
            (record["provider_name"], record["name"], record["country"], record.get("intake_year"))
            for record in records
        }
    ) == len(records)
    for record in records:
        additional_sources = record.get("additional_sources", [])
        OpportunityCreate.model_validate(
            {key: value for key, value in record.items() if key != "additional_sources"}
        )
        assert record["source"]["url"].startswith("https://")
        assert len(record["source"]["relevant_excerpt"].split()) <= 25
        for source in additional_sources:
            assert source["url"].startswith("https://")
            assert len(source["relevant_excerpt"].split()) <= 25


def test_seed_loader_requires_admin_user(db_session: Session) -> None:
    try:
        seed_verified_opportunities(db_session)
    except SeedError as exc:
        assert "Create an admin user" in str(exc)
    else:
        raise AssertionError("Expected missing admin to raise SeedError")


def test_seed_loader_dry_run_validates_without_creating_records(db_session: Session) -> None:
    summary = seed_verified_opportunities(db_session, dry_run=True)

    assert summary["validated"] == 50
    assert summary["created"] == 0
    assert db_session.query(Opportunity).count() == 0


def test_seed_loader_stages_incomplete_records_for_review(db_session: Session) -> None:
    admin = create_admin(db_session)

    summary = seed_verified_opportunities(db_session, admin_email=admin.email)

    opportunities = db_session.query(Opportunity).all()
    assert summary["created"] == summary["validated"]
    assert summary["held_for_review"] == summary["validated"]
    assert len(opportunities) == summary["created"]
    assert all(opportunity.status is OpportunityStatus.DRAFT for opportunity in opportunities)
    assert all(
        opportunity.publication_completeness == "incomplete"
        for opportunity in opportunities
    )
    assert all(
        all(
            source.verification_status is VerificationStatus.NEEDS_REVIEW
            for source in opportunity.sources
        )
        for opportunity in opportunities
    )


def test_seed_loader_skips_duplicates_on_second_run(db_session: Session) -> None:
    admin = create_admin(db_session)
    first = seed_verified_opportunities(db_session, admin_email=admin.email)

    second = seed_verified_opportunities(db_session, admin_email=admin.email)

    assert first["created"] == 50
    assert second["created"] == 0
    assert second["skipped_duplicates"] == first["validated"]


def test_demo_bootstrap_creates_admin_and_loads_catalogue_idempotently(
    db_session: Session,
) -> None:
    email = "demo-admin@example.com"

    admin, first = bootstrap_demo(
        db_session,
        email=email,
        password="DemoBootstrapPassword123",
    )
    repeat_admin, second = bootstrap_demo(
        db_session,
        email=email,
        password="UpdatedDemoBootstrapPassword123",
    )

    assert admin.email == email
    assert admin.role is UserRole.ADMIN
    assert admin.email_verified_at is not None
    assert first["created"] == first["validated"]
    assert second["created"] == 0
    assert second["skipped_duplicates"] == first["validated"]
    assert repeat_admin.id == admin.id
    assert db_session.query(Opportunity).count() == first["validated"]


def test_custom_seed_path_must_contain_records(tmp_path: Path, db_session: Session) -> None:
    create_admin(db_session)
    invalid_seed = tmp_path / "invalid.json"
    invalid_seed.write_text("{}", encoding="utf-8")

    try:
        seed_verified_opportunities(db_session, seed_path=invalid_seed, dry_run=True)
    except SeedError as exc:
        assert "records list" in str(exc)
    else:
        raise AssertionError("Expected invalid seed file to raise SeedError")
