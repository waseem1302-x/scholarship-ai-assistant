import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.core.security import generate_refresh_token, hash_refresh_token
from app.modules.auth.models import AuditLog, User
from app.modules.beta.models import (
    BetaInvitation,
    BetaInvitationStatus,
    BetaLegalAcceptance,
)
from app.modules.beta.schemas import (
    BetaInvitationCreate,
    BetaInvitationDeliveryResponse,
    BetaInvitationResponse,
    BetaPolicyResponse,
)


class BetaService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def policy(self) -> BetaPolicyResponse:
        return BetaPolicyResponse(
            beta_enabled=self.settings.beta_enabled,
            registration_open=self.settings.beta_registration_open,
            max_active_students=self.settings.beta_max_active_students,
            catalogue_maintenance_mode=self.settings.catalogue_maintenance_mode,
            assistant_enabled=self.settings.assistant_enabled,
            document_lab_enabled=self.settings.document_lab_enabled,
            community_enabled=self.settings.community_enabled,
        )

    def create_invitation(
        self, payload: BetaInvitationCreate, actor: User
    ) -> BetaInvitationDeliveryResponse:
        if not self.settings.beta_enabled or not self.settings.beta_registration_open:
            raise AppError(
                "beta_invitations_closed",
                "Invitation intake is currently closed.",
                409,
            )
        self._expire_due()
        self._lock_cohort()
        occupied_seats = (
            self.session.scalar(
                select(func.count(BetaInvitation.id)).where(
                    BetaInvitation.status.in_(
                        (BetaInvitationStatus.PENDING, BetaInvitationStatus.REDEEMED)
                    )
                )
            )
            or 0
        )
        if occupied_seats >= self.settings.beta_max_active_students:
            raise AppError(
                "beta_capacity_reached",
                "The approved beta cohort is currently full.",
                409,
            )
        now = datetime.now(UTC)
        existing = self.session.scalar(
            select(BetaInvitation).where(
                BetaInvitation.email == str(payload.email),
                BetaInvitation.status == BetaInvitationStatus.PENDING,
                BetaInvitation.expires_at > now,
            )
        )
        if existing is not None:
            raise ConflictError(
                "beta_invitation_already_pending",
                "A usable invitation already exists for this email.",
            )
        raw_code = generate_refresh_token()
        invitation = BetaInvitation(
            email=str(payload.email),
            code_hash=hash_refresh_token(raw_code),
            expires_at=now + timedelta(days=payload.expires_in_days),
            created_by_user_id=actor.id,
        )
        self.session.add(invitation)
        self._audit(actor.id, "beta_invitation_created", "beta_invitation", str(invitation.id))
        self.session.commit()
        self.session.refresh(invitation)
        return BetaInvitationDeliveryResponse(
            **self._response_data(invitation), invitation_code=raw_code
        )

    def list_invitations(self) -> list[BetaInvitationResponse]:
        self._expire_due()
        invitations = self.session.scalars(
            select(BetaInvitation).order_by(BetaInvitation.created_at.desc())
        ).all()
        return [BetaInvitationResponse(**self._response_data(item)) for item in invitations]

    def revoke_invitation(self, invitation_id: uuid.UUID, actor: User) -> None:
        invitation = self.session.get(BetaInvitation, invitation_id)
        if invitation is None:
            raise AppError("beta_invitation_not_found", "Invitation was not found.", 404)
        if invitation.status == BetaInvitationStatus.PENDING:
            invitation.status = BetaInvitationStatus.REVOKED
            invitation.revoked_at = datetime.now(UTC)
            self._audit(actor.id, "beta_invitation_revoked", "beta_invitation", str(invitation.id))
            self.session.commit()

    def reserve_for_registration(
        self,
        email: str,
        raw_code: str | None,
        user_id: uuid.UUID,
        accepted_terms: bool,
    ) -> None:
        if not self.settings.beta_enabled:
            return
        if not self.settings.beta_registration_open or not raw_code:
            raise AppError(
                "beta_invitation_required",
                "An active invitation is required to create a beta account.",
                403,
            )
        if not accepted_terms:
            raise AppError(
                "beta_terms_acceptance_required",
                "Accept the beta terms and privacy notice before creating an account.",
                422,
            )
        invitation = self.session.scalar(
            select(BetaInvitation)
            .where(BetaInvitation.code_hash == hash_refresh_token(raw_code))
            .with_for_update()
        )
        now = datetime.now(UTC)
        if (
            invitation is None
            or invitation.email != email
            or invitation.status is not BetaInvitationStatus.PENDING
            or self._as_utc(invitation.expires_at) <= now
            or invitation.redemption_count >= invitation.max_redemptions
            or invitation.reserved_by_user_id is not None
        ):
            raise AppError(
                "beta_invitation_invalid",
                "The invitation is invalid, expired, or no longer available.",
                403,
            )
        invitation.reserved_by_user_id = user_id
        invitation.reserved_at = now
        self.session.add(
            BetaLegalAcceptance(
                user_id=user_id,
                terms_version=self.settings.beta_terms_version,
                privacy_notice_version=self.settings.beta_privacy_notice_version,
            )
        )
        self._audit(user_id, "beta_invitation_reserved", "beta_invitation", str(invitation.id))

    def activate_after_email_verification(self, user_id: uuid.UUID) -> None:
        """Convert a reserved invite into a beta seat only after email verification."""
        if not self.settings.beta_enabled:
            return
        invitation = self.session.scalar(
            select(BetaInvitation)
            .where(
                BetaInvitation.reserved_by_user_id == user_id,
                BetaInvitation.status == BetaInvitationStatus.PENDING,
            )
            .with_for_update()
        )
        if invitation is None:
            return
        now = datetime.now(UTC)
        if self._as_utc(invitation.expires_at) <= now:
            invitation.status = BetaInvitationStatus.EXPIRED
            user = self.session.get(User, user_id)
            if user is not None:
                # An expired reservation must not leave a verified account able
                # to access an invite-only beta. Support can issue a new invite.
                user.is_active = False
            self._audit(user_id, "beta_invitation_expired", "beta_invitation", str(invitation.id))
            return
        invitation.redemption_count += 1
        invitation.redeemed_by_user_id = user_id
        invitation.status = BetaInvitationStatus.REDEEMED
        self._audit(user_id, "beta_invitation_redeemed", "beta_invitation", str(invitation.id))

    def _expire_due(self) -> None:
        now = datetime.now(UTC)
        changed = False
        for invitation in self.session.scalars(
            select(BetaInvitation).where(
                BetaInvitation.status == BetaInvitationStatus.PENDING,
                BetaInvitation.expires_at <= now,
            )
        ):
            invitation.status = BetaInvitationStatus.EXPIRED
            changed = True
        if changed:
            self.session.commit()

    def _audit(
        self,
        actor_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: str,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_user_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata_json={"phase": "beta"},
            )
        )

    def _lock_cohort(self) -> None:
        """Serialize seat allocation on PostgreSQL; SQLite test databases need no lock."""
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            self.session.execute(select(func.pg_advisory_xact_lock(9_000_019)))

    @staticmethod
    def _response_data(invitation: BetaInvitation) -> dict[str, object]:
        return {
            "id": invitation.id,
            "email": invitation.email,
            "status": invitation.status,
            "expires_at": invitation.expires_at,
            "redemption_count": invitation.redemption_count,
            "max_redemptions": invitation.max_redemptions,
            "created_at": invitation.created_at,
            "redeemed_by_user_id": invitation.redeemed_by_user_id,
            "reserved_by_user_id": invitation.reserved_by_user_id,
            "reserved_at": invitation.reserved_at,
        }

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
