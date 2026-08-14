import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.modules.auth.models import AuditLog, User, UserRole
from app.modules.auth.service import AuthService
from app.modules.beta.models import (
    BetaInvitation,
    BetaInvitationStatus,
    BetaLegalAcceptance,
)
from app.modules.beta.schemas import BetaInvitationCreate
from app.modules.beta.service import BetaService


def settings(**changes: object) -> Settings:
    defaults: dict[str, object] = {
        "env": "test",
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": "phase-nine-beta-test-secret-at-least-32-characters",
        "beta_enabled": True,
        "beta_registration_open": True,
    }
    defaults.update(changes)
    return Settings(**defaults)


def admin(session: Session) -> User:
    record = User(
        id=uuid.uuid4(),
        email="phase9-admin@example.com",
        password_hash=hash_password("phase9-admin-password-42"),
        role=UserRole.ADMIN,
    )
    session.add(record)
    session.commit()
    return record


def test_beta_policy_reports_truthful_provider_mode_and_global_caps(
    db_session: Session,
) -> None:
    configuration = settings(
        assistant_global_daily_limit=321,
        document_lab_global_daily_upload_limit=123,
    )

    policy = BetaService(db_session, configuration).policy()

    assert policy.assistant_mode == "source_backed_templates"
    assert policy.assistant_global_daily_limit == 321
    assert policy.document_lab_global_daily_upload_limit == 123


def test_closed_beta_rejects_self_registration(db_session: Session) -> None:
    auth = AuthService(db_session, settings(beta_registration_open=False))

    with pytest.raises(AppError, match="invitation") as error:
        auth.register("closed@example.com", "phase9-password-42")

    assert error.value.code == "beta_invitation_required"


def test_invitation_is_email_bound_single_use_and_audited(db_session: Session) -> None:
    configuration = settings()
    actor = admin(db_session)
    beta = BetaService(db_session, configuration)
    created = beta.create_invitation(BetaInvitationCreate(email="invited@example.com"), actor)

    registered = AuthService(db_session, configuration).register(
        "invited@example.com",
        "phase9-password-42",
        created.invitation_code,
        accept_beta_terms=True,
    )
    invitation = db_session.get(BetaInvitation, created.id)
    assert invitation is not None
    assert invitation.status is BetaInvitationStatus.PENDING
    assert invitation.reserved_by_user_id == registered.user.id
    assert invitation.redeemed_by_user_id is None
    assert invitation.code_hash != created.invitation_code
    acceptance = db_session.scalar(
        select(BetaLegalAcceptance).where(BetaLegalAcceptance.user_id == registered.user.id)
    )
    assert acceptance is not None
    assert acceptance.terms_version == configuration.beta_terms_version
    exported = AuthService(db_session, configuration).export_student_account(registered.user)
    assert exported["beta_legal_acceptances"] == [
        {
            "terms_version": configuration.beta_terms_version,
            "privacy_notice_version": configuration.beta_privacy_notice_version,
            "accepted_at": acceptance.accepted_at.isoformat(),
        }
    ]

    with pytest.raises(AppError) as rejected:
        AuthService(db_session, configuration).register(
            "other@example.com",
            "phase9-password-42",
            created.invitation_code,
            accept_beta_terms=True,
        )
    assert rejected.value.code == "beta_invitation_invalid"
    assert {item.action for item in db_session.scalars(select(AuditLog)).all()} >= {
        "beta_invitation_created",
        "beta_invitation_reserved",
    }


def test_beta_registration_requires_explicit_terms_acceptance(
    db_session: Session,
) -> None:
    configuration = settings()
    actor = admin(db_session)
    created = BetaService(db_session, configuration).create_invitation(
        BetaInvitationCreate(email="terms@example.com"), actor
    )

    with pytest.raises(AppError) as rejected:
        AuthService(db_session, configuration).register(
            "terms@example.com", "phase9-password-42", created.invitation_code
        )
    assert rejected.value.code == "beta_terms_acceptance_required"


def test_invitation_revoke_is_idempotent_and_prevents_redemption(
    db_session: Session,
) -> None:
    configuration = settings()
    actor = admin(db_session)
    beta = BetaService(db_session, configuration)
    created = beta.create_invitation(BetaInvitationCreate(email="revoked@example.com"), actor)
    beta.revoke_invitation(created.id, actor)
    beta.revoke_invitation(created.id, actor)

    with pytest.raises(AppError) as rejected:
        AuthService(db_session, configuration).register(
            "revoked@example.com",
            "phase9-password-42",
            created.invitation_code,
            accept_beta_terms=True,
        )
    assert rejected.value.code == "beta_invitation_invalid"


def test_invitation_creation_respects_approved_cohort_capacity(
    db_session: Session,
) -> None:
    configuration = settings(beta_max_active_students=1)
    actor = admin(db_session)
    BetaService(db_session, configuration).create_invitation(
        BetaInvitationCreate(email="already-in-beta@example.com"), actor
    )

    with pytest.raises(AppError) as full:
        BetaService(db_session, configuration).create_invitation(
            BetaInvitationCreate(email="next@example.com"), actor
        )
    assert full.value.code == "beta_capacity_reached"


def test_verified_email_activates_reserved_beta_seat(db_session: Session) -> None:
    configuration = settings()
    actor = admin(db_session)
    created = BetaService(db_session, configuration).create_invitation(
        BetaInvitationCreate(email="verify-before-beta@example.com"), actor
    )
    auth = AuthService(db_session, configuration)
    registered = auth.register(
        "verify-before-beta@example.com",
        "phase9-password-42",
        created.invitation_code,
        accept_beta_terms=True,
    )
    verification = auth.issue_email_verification(registered.user)

    verified = auth.confirm_email_verification(verification.raw_token)
    invitation = db_session.get(BetaInvitation, created.id)
    assert verified.email_verified_at is not None
    assert invitation is not None
    assert invitation.status is BetaInvitationStatus.REDEEMED
    assert invitation.redeemed_by_user_id == registered.user.id
    assert invitation.redemption_count == 1
    assert {item.action for item in db_session.scalars(select(AuditLog)).all()} >= {
        "beta_invitation_reserved",
        "beta_invitation_redeemed",
    }
