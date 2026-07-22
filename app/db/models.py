"""Import every ORM model here so Alembic can discover complete metadata."""

from app.modules.auth.models import RefreshToken, User
from app.modules.opportunities.models import (
    Opportunity,
    Provider,
    Source,
    University,
    VerificationRecord,
)
from app.modules.profiles.models import StudentProfile

__all__ = [
    "Opportunity",
    "Provider",
    "RefreshToken",
    "Source",
    "StudentProfile",
    "University",
    "User",
    "VerificationRecord",
]
