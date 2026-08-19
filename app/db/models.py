"""Import every ORM model here so Alembic can discover complete metadata."""

from app.modules.catalogue_ingestion.evidence_ledger_models import (
    CatalogueCandidateSourceSnapshot,
    CatalogueClaimAssessment,
    CatalogueClaimEvidence,
    CatalogueClaimResolution,
    CatalogueClaimResolutionMember,
    CatalogueConflictClaim,
    CatalogueConflictReviewDecision,
    CatalogueConflictSet,
    CatalogueEvidenceBundle,
    CatalogueEvidenceBundleClaim,
    CatalogueEvidenceBundleSource,
    CatalogueFieldClaim,
    CatalogueGraphMaterialization,
    CatalogueSnapshotPromotion,
    CatalogueSourceExtraction,
    CatalogueSourceExtractionAttempt,
)

# Existing imports retained below.
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
from app.modules.assistant.models import (
    AssistantAnswer,
    AssistantCitation,
    AssistantConversation,
    AssistantEvaluationRun,
    AssistantEvidencePacket,
    AssistantFeedback,
    AssistantMessage,
    AssistantPrivacyPreference,
)
from app.modules.auth.models import (
    AdminStepUpToken,
    AuditLog,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    WebAuthnChallenge,
    WebAuthnCredential,
)
from app.modules.beta.models import BetaInvitation, BetaLegalAcceptance
from app.modules.catalogue_ingestion.models import (
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
    ClassificationDecision,
)
from app.modules.community.models import (
    CommunityBlock,
    CommunityBookmark,
    CommunityModerationRecord,
    CommunityPost,
    CommunityPreference,
    CommunityReply,
    CommunityReport,
)
from app.modules.document_lab.models import (
    ApplicationDocumentLink,
    DocumentAnalysis,
    DocumentAnalysisJob,
    DocumentAsset,
    DocumentConsent,
    DocumentExtraction,
    DocumentFeedbackItem,
    DocumentVersion,
)
from app.modules.matching.models import MatchEvaluation, MatchEvaluationResult, MatchRuleOutcome
from app.modules.operations.models import OperationalJobHealth
from app.modules.opportunities.evidence_models import (
    ApplicationStep,
    FieldEvidence,
    FundingComponent,
    RequiredDocument,
    ScopedDeadline,
    SourceSnapshot,
)
from app.modules.opportunities.graph_models import (
    AcademicProgramme,
    ApplicationTrack,
    Institution,
    InstitutionAlias,
    InstitutionParticipation,
    ScholarshipAlias,
    ScholarshipRelationship,
    TrackProgramme,
)
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
    name
    for name in globals()
    if not name.startswith("_")
]
