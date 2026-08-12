"""Import every ORM model here so Alembic can discover complete metadata."""

from app.modules.applications.models import SavedOpportunity
from app.modules.auth.models import (
    AdminStepUpToken,
    AuditLog,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
)
from app.modules.matching.models import MatchEvaluation, MatchEvaluationResult, MatchRuleOutcome
from app.modules.opportunities.models import (
    EligibilityRule,
    Opportunity,
    OpportunityCycle,
    Provider,
    Source,
    SourceExcerpt,
    University,
    VerificationRecord,
)
from app.modules.profiles.models import StudentProfile

__all__ = [
    "AdminStepUpToken",
    "AuditLog",
    "EligibilityRule",
    "EmailVerificationToken",
    "MatchEvaluation",
    "MatchEvaluationResult",
    "MatchRuleOutcome",
    "Opportunity",
    "OpportunityCycle",
    "PasswordResetToken",
    "Provider",
    "RefreshToken",
    "SavedOpportunity",
    "Source",
    "SourceExcerpt",
    "StudentProfile",
    "University",
    "User",
    "VerificationRecord",
]
