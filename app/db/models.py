"""Import every ORM model here so Alembic can discover complete metadata."""

from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    ApplicationNotificationPreference,
    ApplicationReminder,
    ApplicationTask,
    ReminderWorkerHealth,
    SavedOpportunity,
)
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
    "Application",
    "ApplicationDocument",
    "ApplicationEvent",
    "ApplicationNotificationPreference",
    "ApplicationReminder",
    "ApplicationTask",
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
    "ReminderWorkerHealth",
    "SavedOpportunity",
    "Source",
    "SourceExcerpt",
    "StudentProfile",
    "University",
    "User",
    "VerificationRecord",
]
