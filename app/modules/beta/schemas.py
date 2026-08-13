import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.modules.beta.models import BetaInvitationStatus


class BetaInvitationCreate(BaseModel):
    email: EmailStr
    expires_in_days: int = Field(default=14, ge=1, le=90)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class BetaInvitationResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    status: BetaInvitationStatus
    expires_at: datetime
    redemption_count: int
    max_redemptions: int
    created_at: datetime
    redeemed_by_user_id: uuid.UUID | None = None
    reserved_by_user_id: uuid.UUID | None = None
    reserved_at: datetime | None = None


class BetaInvitationDeliveryResponse(BetaInvitationResponse):
    # Return once to an authenticated administrator only. The raw code is not
    # persisted and never appears in audit metadata or list responses.
    invitation_code: str


class BetaPolicyResponse(BaseModel):
    beta_enabled: bool
    registration_open: bool
    max_active_students: int
    catalogue_maintenance_mode: bool
    assistant_enabled: bool
    document_lab_enabled: bool
    community_enabled: bool
