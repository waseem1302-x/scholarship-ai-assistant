import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.applications.models import Application, TaskStatus
from app.modules.assistant.models import (
    AssistantAnswer,
    AssistantAnswerStatus,
    AssistantCitation,
    AssistantConversation,
    AssistantEvidencePacket,
    AssistantFeedback,
    AssistantMessage,
    AssistantMessageRole,
    AssistantPrivacyPreference,
)
from app.modules.assistant.provider import (
    AssistantProviderError,
    EvidenceOnlyProvider,
    get_provider,
)
from app.modules.assistant.schemas import (
    AssistantAnswerRequest,
    AssistantAnswerResponse,
    AssistantPreferenceResponse,
    AssistantPreferenceUpdate,
    AssistantStructuredResponse,
    CitationResponse,
    ConversationDetailResponse,
    ConversationSummaryResponse,
    FactResponse,
    FeedbackRequest,
    PossibleMatchResponse,
    PrivateProgressItemResponse,
    RequirementResponse,
    SaveAnswerResponse,
)
from app.modules.auth.models import User, utc_now
from app.modules.opportunities.lifecycle import effective_application_window
from app.modules.opportunities.models import (
    ApplicationWindowState,
    Opportunity,
    OpportunityStatus,
    Source,
    SourceExcerpt,
    SourceType,
    VerificationStatus,
)
from app.modules.profiles.models import StudentProfile


class AssistantService:
    """Creates only traceable answers from verified structured catalogue records."""

    BLOCKED_TERMS = (
        "review my cv",
        "review my sop",
        "score my cv",
        "score my essay",
        "write my sop",
        "write my essay",
        "plagiarism",
        "visa advice",
        "legal advice",
        "guarantee admission",
        "guarantee funding",
    )

    def __init__(
        self, session: Session, settings: Settings, provider: EvidenceOnlyProvider | None = None
    ) -> None:
        self.session = session
        self.settings = settings
        self.provider = provider or get_provider(settings)

    def answer(self, payload: AssistantAnswerRequest, user: User) -> AssistantAnswerResponse:
        self._purge_expired_data()
        self._require_consent(user.id)
        self._enforce_quota(user.id)
        conversation = self._conversation_for_request(payload.conversation_id, user.id)
        question = payload.question.strip()
        blocked = any(term in question.casefold() for term in self.BLOCKED_TERMS)
        answer_type = self._answer_type(question, payload.selected_opportunity_ids)
        opportunities, skipped = self._retrieve(question, payload.selected_opportunity_ids)
        packet = AssistantEvidencePacket(
            user_id=user.id,
            query_interpretation={
                "question_length": len(question),
                "tokens": self._query_tokens(question),
                "profile_requested": payload.use_profile,
                "application_data_requested": payload.use_application_data,
                "answer_type": answer_type,
            },
            scholarship_ids=[str(item.id) for item, _ in opportunities],
            source_snapshots=[
                self._source_snapshot(item, source) for item, source in opportunities
            ],
            freshness_status={"accepted": len(opportunities), "rejected": skipped},
            conflicts=[],
            retrieval_version=self.settings.assistant_retrieval_version,
            rule_version="official-source-freshness.v1",
        )
        self.session.add(packet)
        self.session.flush()

        if blocked:
            response = self._blocked_response()
            status = AssistantAnswerStatus.BLOCKED
            citation_specs: list[tuple[Opportunity, Source, str]] = []
        elif answer_type in {
            "application task prioritization",
            "private application progress summary",
        }:
            response, citation_specs = self._private_progress_response(
                user.id, enabled=payload.use_application_data, answer_type=answer_type
            )
            status = AssistantAnswerStatus.COMPLETED
        elif answer_type == "what changed from source monitoring":
            response = self._source_change_unavailable_response()
            citation_specs = []
            status = AssistantAnswerStatus.ABSTAINED
        elif not opportunities:
            response = self._abstained_response(skipped)
            status = AssistantAnswerStatus.ABSTAINED
            citation_specs = []
        else:
            profile = self._profile(user.id) if payload.use_profile else None
            response, citation_specs = self._compose_response(
                question, opportunities, profile, answer_type=answer_type
            )
            try:
                response = AssistantStructuredResponse.model_validate(
                    self.provider.generate(response).model_dump()
                )
                status = AssistantAnswerStatus.COMPLETED
            except AssistantProviderError:
                response = self._provider_unavailable_response()
                citation_specs = []
                status = AssistantAnswerStatus.FAILED

        answer = AssistantAnswer(
            user_id=user.id,
            conversation_id=conversation.id,
            evidence_packet_id=packet.id,
            status=status,
            provider=self.provider.name,
            model_version=self.provider.model_version,
            prompt_template_version=self.settings.assistant_prompt_version,
            retrieval_version=self.settings.assistant_retrieval_version,
            response_json={},
            failure_code="provider_unavailable" if status is AssistantAnswerStatus.FAILED else None,
        )
        self.session.add(answer)
        self.session.flush()
        citations = self._store_citations(answer, citation_specs)
        response = self._attach_citations(response, citations)
        answer.response_json = response.model_dump(mode="json")
        if conversation.history_enabled:
            self.session.add(
                AssistantMessage(
                    conversation_id=conversation.id,
                    role=AssistantMessageRole.USER,
                    content=question,
                )
            )
            self.session.add(
                AssistantMessage(
                    conversation_id=conversation.id,
                    role=AssistantMessageRole.ASSISTANT,
                    content=response.answer,
                )
            )
        self.session.commit()
        return self._answer_response(answer, response)

    def list_conversations(self, user_id: uuid.UUID) -> list[ConversationSummaryResponse]:
        self._purge_expired_data()
        rows = self.session.scalars(
            select(AssistantConversation)
            .where(
                AssistantConversation.user_id == user_id,
                AssistantConversation.history_enabled.is_(True),
            )
            .order_by(AssistantConversation.updated_at.desc())
        ).all()
        return [ConversationSummaryResponse.model_validate(row) for row in rows]

    def get_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> ConversationDetailResponse:
        self._purge_expired_data()
        conversation = self._owned_conversation(conversation_id, user_id)
        answers = self.session.scalars(
            select(AssistantAnswer)
            .where(AssistantAnswer.conversation_id == conversation.id)
            .order_by(AssistantAnswer.created_at)
        ).all()
        return ConversationDetailResponse(
            **ConversationSummaryResponse.model_validate(conversation).model_dump(),
            answers=[self._answer_response(answer) for answer in answers],
        )

    def save_answer(self, answer_id: uuid.UUID, user_id: uuid.UUID) -> SaveAnswerResponse:
        answer = self._owned_answer(answer_id, user_id)
        answer.saved_to_workspace = True
        answer.saved_at = utc_now()
        self.session.commit()
        return SaveAnswerResponse(id=answer.id, saved_to_workspace=True, saved_at=answer.saved_at)

    def feedback(self, answer_id: uuid.UUID, payload: FeedbackRequest, user_id: uuid.UUID) -> None:
        self._owned_answer(answer_id, user_id)
        self.session.add(
            AssistantFeedback(
                answer_id=answer_id,
                user_id=user_id,
                feedback_type=payload.feedback_type,
                comment=payload.comment.strip() if payload.comment else None,
                expires_at=utc_now()
                + timedelta(days=self.settings.assistant_feedback_retention_days),
            )
        )
        self.session.commit()

    def set_history(self, user_id: uuid.UUID, enabled: bool) -> None:
        preference = self._preference_for_user(user_id, create=True)
        preference.history_enabled = enabled
        if not enabled:
            # Disabling history immediately removes retained text, while answer audit
            # metadata remains citation-only and user-owned for deletion/export.
            conversations = self.session.scalars(
                select(AssistantConversation).where(AssistantConversation.user_id == user_id)
            ).all()
            for conversation in conversations:
                conversation.history_enabled = False
                self.session.execute(
                    delete(AssistantMessage).where(
                        AssistantMessage.conversation_id == conversation.id
                    )
                )
        self.session.commit()

    def get_preferences(self, user_id: uuid.UUID) -> AssistantPreferenceResponse:
        preference = self._preference_for_user(user_id)
        return AssistantPreferenceResponse(
            consented=bool(preference and preference.consented_at),
            history_enabled=preference.history_enabled if preference else True,
            history_retention_days=self.settings.assistant_history_retention_days,
            feedback_retention_days=self.settings.assistant_feedback_retention_days,
        )

    def update_preferences(
        self, user_id: uuid.UUID, payload: AssistantPreferenceUpdate
    ) -> AssistantPreferenceResponse:
        preference = self._preference_for_user(user_id, create=True)
        if payload.consent is True:
            preference.consented_at = utc_now()
        if payload.history_enabled is not None:
            self.set_history(user_id, payload.history_enabled)
        self.session.commit()
        return self.get_preferences(user_id)

    def delete_conversation(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        conversation = self._owned_conversation(conversation_id, user_id)
        answer_ids = self.session.scalars(
            select(AssistantAnswer.id).where(AssistantAnswer.conversation_id == conversation.id)
        ).all()
        self.session.execute(
            delete(AssistantFeedback).where(AssistantFeedback.answer_id.in_(answer_ids))
        )
        self.session.delete(conversation)
        self.session.commit()

    def export_data(self, user_id: uuid.UUID) -> list[ConversationDetailResponse]:
        conversations = self.session.scalars(
            select(AssistantConversation)
            .where(AssistantConversation.user_id == user_id)
            .order_by(AssistantConversation.created_at)
        ).all()
        return [self.get_conversation(conversation.id, user_id) for conversation in conversations]

    def delete_all_data(self, user_id: uuid.UUID) -> None:
        answer_ids = self.session.scalars(
            select(AssistantAnswer.id).where(AssistantAnswer.user_id == user_id)
        ).all()
        self.session.execute(delete(AssistantFeedback).where(AssistantFeedback.user_id == user_id))
        self.session.execute(
            delete(AssistantCitation).where(AssistantCitation.answer_id.in_(answer_ids))
        )
        self.session.execute(delete(AssistantAnswer).where(AssistantAnswer.user_id == user_id))
        self.session.execute(
            delete(AssistantEvidencePacket).where(AssistantEvidencePacket.user_id == user_id)
        )
        self.session.execute(
            delete(AssistantConversation).where(AssistantConversation.user_id == user_id)
        )
        self.session.commit()

    def _enforce_quota(self, user_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        daily = (
            self.session.scalar(
                select(func.count(AssistantAnswer.id)).where(
                    AssistantAnswer.user_id == user_id,
                    AssistantAnswer.created_at >= now - timedelta(days=1),
                )
            )
            or 0
        )
        monthly = (
            self.session.scalar(
                select(func.count(AssistantAnswer.id)).where(
                    AssistantAnswer.user_id == user_id,
                    AssistantAnswer.created_at >= now - timedelta(days=30),
                )
            )
            or 0
        )
        if (
            daily >= self.settings.assistant_daily_user_limit
            or monthly >= self.settings.assistant_monthly_user_limit
        ):
            raise AppError(
                "assistant_quota_exceeded", "Assistant request limit reached. Try again later.", 429
            )

    def _conversation_for_request(
        self, conversation_id: uuid.UUID | None, user_id: uuid.UUID
    ) -> AssistantConversation:
        if conversation_id:
            return self._owned_conversation(conversation_id, user_id)
        preference = self._preference_for_user(user_id)
        history_enabled = preference.history_enabled if preference else True
        conversation = AssistantConversation(
            user_id=user_id,
            history_enabled=history_enabled,
            expires_at=(
                utc_now() + timedelta(days=self.settings.assistant_history_retention_days)
                if history_enabled
                else None
            ),
        )
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def _owned_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> AssistantConversation:
        conversation = self.session.get(AssistantConversation, conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise AppError(
                "assistant_conversation_not_found", "Assistant conversation was not found", 404
            )
        return conversation

    def _owned_answer(self, answer_id: uuid.UUID, user_id: uuid.UUID) -> AssistantAnswer:
        answer = self.session.get(AssistantAnswer, answer_id)
        if answer is None or answer.user_id != user_id:
            raise AppError("assistant_answer_not_found", "Assistant answer was not found", 404)
        return answer

    def _preference_for_user(
        self, user_id: uuid.UUID, *, create: bool = False
    ) -> AssistantPrivacyPreference | None:
        preference = self.session.get(AssistantPrivacyPreference, user_id)
        if preference is None and create:
            preference = AssistantPrivacyPreference(user_id=user_id)
            self.session.add(preference)
            self.session.flush()
        return preference

    def _require_consent(self, user_id: uuid.UUID) -> None:
        preference = self._preference_for_user(user_id)
        if preference is None or preference.consented_at is None:
            raise AppError(
                "assistant_consent_required",
                "Review and accept the assistant data-use notice before asking a question.",
                403,
            )

    def _purge_expired_data(self) -> None:
        """Enforce retention without logging chat contents or private profile data."""
        now = utc_now()
        for feedback in self.session.scalars(
            select(AssistantFeedback).where(
                AssistantFeedback.expires_at.is_not(None), AssistantFeedback.expires_at <= now
            )
        ).all():
            self.session.delete(feedback)
        for conversation in self.session.scalars(
            select(AssistantConversation).where(
                AssistantConversation.expires_at.is_not(None),
                AssistantConversation.expires_at <= now,
            )
        ).all():
            self.session.execute(
                delete(AssistantMessage).where(AssistantMessage.conversation_id == conversation.id)
            )
            conversation.history_enabled = False
            conversation.expires_at = None
        audit_cutoff = now - timedelta(days=self.settings.assistant_audit_retention_days)
        packet_ids_in_use = select(AssistantAnswer.evidence_packet_id)
        self.session.execute(
            delete(AssistantEvidencePacket).where(
                AssistantEvidencePacket.created_at < audit_cutoff,
                AssistantEvidencePacket.id.not_in(packet_ids_in_use),
            )
        )
        self.session.commit()

    def _retrieve(
        self, question: str, selected_opportunity_ids: list[uuid.UUID]
    ) -> tuple[list[tuple[Opportunity, Source]], dict[str, int]]:
        tokens = self._query_tokens(question)
        statement = (
            select(Opportunity)
            .options(
                selectinload(Opportunity.sources),
                selectinload(Opportunity.provider),
                selectinload(Opportunity.cycles),
                selectinload(Opportunity.eligibility_rules),
            )
            .where(Opportunity.status == OpportunityStatus.ACTIVE)
        )
        if selected_opportunity_ids:
            statement = statement.where(Opportunity.id.in_(selected_opportunity_ids))
        elif tokens:
            predicates = []
            for token in tokens[:6]:
                value = f"%{token}%"
                predicates.extend(
                    (
                        Opportunity.name.ilike(value),
                        Opportunity.country.ilike(value),
                        Opportunity.field_eligibility.ilike(value),
                        Opportunity.nationality_eligibility.ilike(value),
                    )
                )
            statement = statement.where(or_(*predicates))
        candidates = self.session.scalars(statement).unique().all()
        accepted: list[tuple[Opportunity, Source]] = []
        rejected = {"unverified": 0, "stale": 0, "conflicting_or_expired": 0}
        for opportunity in candidates:
            official_sources = [
                source
                for source in opportunity.sources
                if source.source_type is SourceType.OFFICIAL
            ]
            if any(
                source.verification_status
                in {
                    VerificationStatus.CONFLICTING_INFORMATION,
                    VerificationStatus.EXPIRED,
                    VerificationStatus.ARCHIVED,
                }
                for source in official_sources
            ):
                rejected["conflicting_or_expired"] += 1
                continue
            source = self._approved_source(opportunity)
            if source is None:
                rejected["unverified"] += 1
                continue
            if not self._is_fresh(source):
                rejected["stale"] += 1
                continue
            accepted.append((opportunity, source))
        return accepted[: self.settings.assistant_max_retrieval_results], rejected

    def _compose_response(
        self,
        question: str,
        opportunities: list[tuple[Opportunity, Source]],
        profile: StudentProfile | None,
        *,
        answer_type: str,
    ) -> tuple[AssistantStructuredResponse, list[tuple[Opportunity, Source, str, str]]]:
        citations: list[tuple[Opportunity, Source, str, str]] = []
        facts: list[FactResponse] = []
        matches: list[PossibleMatchResponse] = []
        requirements: list[RequirementResponse] = []
        warnings: list[str] = []
        for opportunity, source in opportunities[:3]:
            listed_degree = opportunity.degree_level.value.replace("_", " ")
            claim = (
                f"{opportunity.name} is listed for {listed_degree} study in {opportunity.country}."
            )
            citations.append((opportunity, source, claim, "degree_country"))
            citation_ref = uuid.uuid4()  # replaced by persisted IDs before return
            text = claim
            facts.append(FactResponse(text=text, citation_ids=[citation_ref]))
            window = effective_application_window(opportunity, source)
            if (
                answer_type == "deadline/status explanation"
                and opportunity.application_deadline
                and window.state in {ApplicationWindowState.OPEN, ApplicationWindowState.UPCOMING}
            ):
                deadline_claim = (
                    f"The recorded application deadline for {opportunity.name} is "
                    f"{opportunity.application_deadline.date().isoformat()}."
                )
                citations.append((opportunity, source, deadline_claim, "application_deadline"))
                facts.append(FactResponse(text=deadline_claim, citation_ids=[uuid.uuid4()]))
            if answer_type == "funding coverage explanation" and opportunity.tuition_coverage:
                funding_claim = (
                    f"Listed tuition coverage for {opportunity.name}: "
                    f"{opportunity.tuition_coverage}"
                )
                citations.append((opportunity, source, funding_claim, "tuition_coverage"))
                facts.append(FactResponse(text=funding_claim, citation_ids=[uuid.uuid4()]))
            if answer_type == "requirements checklist explanation":
                for key, label, value in (
                    ("field_eligibility", "field eligibility", opportunity.field_eligibility),
                    (
                        "nationality_eligibility",
                        "nationality eligibility",
                        opportunity.nationality_eligibility,
                    ),
                    (
                        "english_language_requirement",
                        "English language requirement",
                        opportunity.english_language_requirement,
                    ),
                ):
                    if value:
                        requirement_claim = f"Listed {label} for {opportunity.name}: {value}"
                        citations.append((opportunity, source, requirement_claim, key))
                        facts.append(
                            FactResponse(text=requirement_claim, citation_ids=[uuid.uuid4()])
                        )
            reason, profile_warnings = self._profile_match_reason(opportunity, profile)
            warnings.extend(profile_warnings)
            matches.append(
                PossibleMatchResponse(
                    opportunity_id=opportunity.id,
                    name=opportunity.name,
                    reason=reason,
                    citation_ids=[citation_ref],
                )
            )
            if opportunity.required_documents:
                document_claim = (
                    f"The listed required documents for {opportunity.name} are "
                    f"{', '.join(opportunity.required_documents[:4])}."
                )
                citations.append((opportunity, source, document_claim, "required_documents"))
                requirements.append(
                    RequirementResponse(text=document_claim, citation_ids=[uuid.uuid4()])
                )
            if window.state is ApplicationWindowState.DEADLINE_UNKNOWN:
                warnings.append(
                    f"Deadline unknown for {opportunity.name}; recheck the official source."
                )
            elif window.state is ApplicationWindowState.CLOSED:
                warnings.append(
                    f"The recorded deadline for {opportunity.name} has passed; "
                    "confirm the next cycle."
                )
        answer = self._answer_intro(answer_type, len(opportunities))
        return AssistantStructuredResponse(
            answer=answer[: self.settings.assistant_max_response_characters],
            answer_type=answer_type,
            confidence="medium",
            facts=facts,
            possible_matches=matches,
            requirements_to_check=requirements,
            next_actions=[
                "Open the official source for each possible match.",
                self._next_action(answer_type),
            ],
            warnings=list(dict.fromkeys(warnings)),
            citations=[],
            abstained_reason=None,
        ), citations

    def _private_progress_response(
        self, user_id: uuid.UUID, *, enabled: bool, answer_type: str
    ) -> tuple[AssistantStructuredResponse, list[tuple[Opportunity, Source, str, str]]]:
        if not enabled:
            return (
                AssistantStructuredResponse(
                    answer=(
                        "Private application data was not enabled for this question, so I did not "
                        "read your application workspace."
                    ),
                    answer_type=answer_type,
                    confidence="high",
                    warnings=[
                        "Enable private application data only when you want a progress summary."
                    ],
                    next_actions=["Ask again with private application data enabled."],
                    abstained_reason="private_application_data_not_enabled",
                ),
                [],
            )
        applications = self.session.scalars(
            select(Application)
            .options(selectinload(Application.opportunity), selectinload(Application.tasks))
            .where(Application.user_id == user_id)
            .order_by(Application.updated_at.desc())
        ).all()
        progress = [
            PrivateProgressItemResponse(
                opportunity_id=item.opportunity_id,
                name=item.opportunity.name,
                lifecycle=item.lifecycle.value.replace("_", " "),
                outstanding_tasks=sum(
                    task.status not in {TaskStatus.COMPLETED, TaskStatus.DISMISSED}
                    for task in item.tasks
                ),
            )
            for item in applications
        ]
        if not progress:
            return (
                AssistantStructuredResponse(
                    answer="You do not have any private applications in your workspace yet.",
                    answer_type=answer_type,
                    confidence="high",
                    next_actions=[
                        "Save a verified scholarship before creating an application plan."
                    ],
                ),
                [],
            )
        outstanding = sum(item.outstanding_tasks for item in progress)
        return (
            AssistantStructuredResponse(
                answer=self._private_progress_intro(answer_type, len(progress), outstanding),
                answer_type=answer_type,
                confidence="high",
                private_progress=progress,
                next_actions=[
                    "Open the application with the most urgent outstanding task."
                    if answer_type == "application task prioritization"
                    else "Open an application to update its tasks or lifecycle."
                ],
                warnings=[
                    "This summary uses only your own application workspace; it has no citations."
                ],
            ),
            [],
        )

    @staticmethod
    def _private_progress_intro(answer_type: str, applications: int, outstanding: int) -> str:
        if answer_type == "application task prioritization":
            return (
                f"Your private workspace has {outstanding} outstanding task(s) across "
                f"{applications} application(s); review the urgent items first."
            )
        return (
            f"Your private workspace contains {applications} application(s) with "
            f"{outstanding} outstanding task(s)."
        )

    @staticmethod
    def _profile_match_reason(
        opportunity: Opportunity, profile: StudentProfile | None
    ) -> tuple[str, list[str]]:
        if profile is None:
            return "It matches terms in your question.", []
        matches: list[str] = []
        missing: list[str] = []
        if profile.target_degree_level:
            if profile.target_degree_level.value == opportunity.degree_level.value:
                matches.append("target degree")
        else:
            missing.append("target degree")
        if profile.intended_field:
            if (
                opportunity.field_eligibility
                and profile.intended_field.casefold() in opportunity.field_eligibility.casefold()
            ):
                matches.append("intended field")
        else:
            missing.append("intended field")
        if profile.nationality:
            if (
                opportunity.nationality_eligibility
                and profile.nationality.casefold() in opportunity.nationality_eligibility.casefold()
            ):
                matches.append("nationality")
        else:
            missing.append("nationality")
        rules = {rule.rule_type.value for rule in opportunity.eligibility_rules}
        profile_values = {
            "cgpa": profile.cgpa,
            "percentage": profile.percentage,
            "ielts": profile.ielts_score,
            "toefl": profile.toefl_score,
            "work_experience_months": profile.work_experience_months,
            "current_education_level": profile.current_education_level,
            "study_mode": profile.preferred_study_mode,
            "intake_year": profile.target_intake_year,
        }
        for key, value in profile_values.items():
            if key in rules:
                if value is None:
                    missing.append(key.replace("_", " "))
                else:
                    matches.append(key.replace("_", " "))
        reason = "It matches terms in your question."
        if matches:
            reason = "Profile signals considered: " + ", ".join(matches)
            reason += "; confirm every official condition."
        warnings = []
        if missing:
            missing_values = ", ".join(sorted(set(missing)))
            warnings.append(
                f"Profile data still needed to assess listed conditions: {missing_values}."
            )
        return reason, warnings

    @staticmethod
    def _blocked_response() -> AssistantStructuredResponse:
        return AssistantStructuredResponse(
            answer=(
                "I can help with source-backed scholarship information, but I "
                "cannot review application documents, provide legal or visa advice, "
                "or guarantee outcomes."
            ),
            answer_type="unsupported_request",
            confidence="high",
            warnings=["This request is outside the assistant's supported scope."],
            abstained_reason="unsupported_request",
        )

    @staticmethod
    def _abstained_response(skipped: dict[str, int]) -> AssistantStructuredResponse:
        warning = "No current verified official-source evidence matched this question."
        if skipped.get("stale") or skipped.get("conflicting_or_expired"):
            warning = (
                "Relevant records need source recheck or contain information "
                "that cannot safely be used."
            )
        return AssistantStructuredResponse(
            answer="I cannot provide a source-backed answer from the verified catalogue right now.",
            answer_type="abstention",
            confidence="high",
            warnings=[warning],
            next_actions=[
                "Try a country, degree level, field, or scholarship name.",
                "Check the official provider directly for current requirements.",
            ],
            abstained_reason="insufficient_current_verified_evidence",
        )

    @staticmethod
    def _provider_unavailable_response() -> AssistantStructuredResponse:
        return AssistantStructuredResponse(
            answer="The assistant provider is unavailable, so I cannot safely generate a response.",
            answer_type="provider_unavailable",
            confidence="high",
            warnings=[
                "No source-backed answer was generated. Try again later or use the catalogue."
            ],
            abstained_reason="provider_unavailable",
        )

    @staticmethod
    def _source_change_unavailable_response() -> AssistantStructuredResponse:
        return AssistantStructuredResponse(
            answer=(
                "I cannot state what changed because this catalogue does not yet retain "
                "a reviewed before-and-after source history for this record."
            ),
            answer_type="what changed from source monitoring",
            confidence="high",
            warnings=["Use the current official source; changes must be curator-verified first."],
            next_actions=["Compare the current official page with your prior saved source."],
            abstained_reason="source_change_history_unavailable",
        )

    def _store_citations(
        self, answer: AssistantAnswer, specs: list[tuple[Opportunity, Source, str, str]]
    ) -> list[AssistantCitation]:
        citations: list[AssistantCitation] = []
        for opportunity, source, claim, claim_key in specs:
            excerpt = max(source.excerpts, key=lambda item: item.captured_at, default=None)
            citation = AssistantCitation(
                answer_id=answer.id,
                opportunity_id=opportunity.id,
                source_id=source.id,
                source_excerpt_id=excerpt.id if excerpt else None,
                claim=claim,
                claim_key=claim_key,
            )
            self.session.add(citation)
            citations.append(citation)
        self.session.flush()
        return citations

    def _attach_citations(
        self, response: AssistantStructuredResponse, citations: list[AssistantCitation]
    ) -> AssistantStructuredResponse:
        citation_models = [self._citation_response(item) for item in citations]
        by_opportunity = {
            item.opportunity_id: item.id for item in citations if item.claim_key == "degree_country"
        }
        for fact in response.facts:
            citation = next((item for item in citations if item.claim == fact.text), None)
            if citation:
                fact.citation_ids = [citation.id]
        for match in response.possible_matches:
            citation_id = by_opportunity.get(match.opportunity_id)
            if citation_id:
                match.citation_ids = [citation_id]
        for requirement in response.requirements_to_check:
            for citation in citations:
                if (
                    citation.claim_key == "required_documents"
                    and citation.claim == requirement.text
                ):
                    requirement.citation_ids = [citation.id]
        response.citations = citation_models
        return response

    def _citation_response(self, citation: AssistantCitation) -> CitationResponse:
        source = self.session.get(Source, citation.source_id)
        assert source is not None
        excerpt = (
            self.session.get(SourceExcerpt, citation.source_excerpt_id)
            if citation.source_excerpt_id
            else None
        )
        return CitationResponse(
            id=citation.id,
            opportunity_id=citation.opportunity_id,
            source_id=source.id,
            source_excerpt_id=citation.source_excerpt_id,
            claim=citation.claim,
            claim_key=citation.claim_key,
            source_title=source.title,
            source_url=source.url,
            excerpt=excerpt.text if excerpt else source.relevant_excerpt,
            last_verified_at=source.last_verified_at,
            freshness="current" if self._is_fresh(source) else "source needs recheck",
        )

    def _answer_response(
        self, answer: AssistantAnswer, response: AssistantStructuredResponse | None = None
    ) -> AssistantAnswerResponse:
        return AssistantAnswerResponse(
            id=answer.id,
            conversation_id=answer.conversation_id,
            status=answer.status,
            provider=answer.provider,
            model_version=answer.model_version,
            prompt_template_version=answer.prompt_template_version,
            retrieval_version=answer.retrieval_version,
            evidence_packet_id=answer.evidence_packet_id,
            created_at=answer.created_at,
            saved_to_workspace=answer.saved_to_workspace,
            response=response or AssistantStructuredResponse.model_validate(answer.response_json),
        )

    def _approved_source(self, opportunity: Opportunity) -> Source | None:
        sources = [
            source
            for source in opportunity.sources
            if source.source_type is SourceType.OFFICIAL
            and source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
        ]
        return max(
            sources,
            key=lambda source: source.last_verified_at or source.date_collected,
            default=None,
        )

    def _is_fresh(self, source: Source) -> bool:
        verified_at = source.last_verified_at
        if verified_at and verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
        return bool(
            verified_at
            and verified_at
            >= datetime.now(UTC) - timedelta(days=self.settings.assistant_source_freshness_days)
        )

    def _profile(self, user_id: uuid.UUID) -> StudentProfile | None:
        return self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))

    @staticmethod
    def _query_tokens(question: str) -> list[str]:
        ignored = {
            "a",
            "an",
            "and",
            "are",
            "for",
            "from",
            "how",
            "i",
            "in",
            "is",
            "me",
            "of",
            "or",
            "scholarship",
            "scholarships",
            "the",
            "to",
            "what",
            "with",
        }
        return [
            token
            for token in re.findall(r"[a-z0-9]{3,}", question.casefold())
            if token not in ignored
        ]

    @staticmethod
    def _answer_type(question: str, selected_opportunity_ids: list[uuid.UUID] | None = None) -> str:
        lowered = question.casefold()
        if selected_opportunity_ids and len(selected_opportunity_ids) > 1:
            return "comparison of selected scholarships"
        if "changed" in lowered:
            return "what changed from source monitoring"
        if "prioriti" in lowered or "task" in lowered:
            return "application task prioritization"
        if "progress" in lowered:
            return "private application progress summary"
        if selected_opportunity_ids:
            return "scholarship detail explanation"
        if "deadline" in lowered or "open" in lowered:
            return "deadline/status explanation"
        if "fund" in lowered or "coverage" in lowered:
            return "funding coverage explanation"
        if "document" in lowered or "requirement" in lowered:
            return "requirements checklist explanation"
        return "scholarship search"

    @staticmethod
    def _answer_intro(answer_type: str, result_count: int) -> str:
        labels = {
            "deadline/status explanation": (
                "Here is the recorded deadline status from current verified sources."
            ),
            "funding coverage explanation": (
                "Here is the funding coverage stated in current verified records."
            ),
            "requirements checklist explanation": (
                "Here are the stated requirements and document checks to confirm."
            ),
            "comparison of selected scholarships": (
                "Here is a source-backed comparison of the selected scholarships."
            ),
            "scholarship detail explanation": (
                "Here is the source-backed detail for the selected scholarship."
            ),
            "what changed from source monitoring": (
                "Changed sources are excluded until reviewed; verified records are shown below."
            ),
            "private application progress summary": (
                "Private application progress is informational and never creates tasks "
                "or reminders."
            ),
        }
        return labels.get(
            answer_type,
            f"I found {result_count} verified catalogue "
            f"record{'s' if result_count != 1 else ''} that may help.",
        )

    @staticmethod
    def _next_action(answer_type: str) -> str:
        if answer_type == "deadline/status explanation":
            return (
                "Confirm the cycle-specific deadline directly on the official source "
                "before applying."
            )
        if answer_type == "funding coverage explanation":
            return "Confirm all included and excluded funding items directly with the provider."
        if answer_type == "requirements checklist explanation":
            return (
                "Confirm nationality, cycle-specific eligibility, and current documents "
                "before applying."
            )
        return (
            "Confirm nationality, cycle-specific eligibility, funding, and the current deadline "
            "before applying."
        )

    @staticmethod
    def _source_snapshot(opportunity: Opportunity, source: Source) -> dict:
        return {
            "opportunity_id": str(opportunity.id),
            "source_id": str(source.id),
            "url": source.url,
            "excerpt": source.relevant_excerpt[:1000],
            "last_verified_at": source.last_verified_at.isoformat()
            if source.last_verified_at
            else None,
        }
