import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.modules.auth.models import AuditLog, User, UserRole
from app.modules.community.models import (
    CommunityBlock,
    CommunityBookmark,
    CommunityContentStatus,
    CommunityModerationAction,
    CommunityModerationRecord,
    CommunityPost,
    CommunityPreference,
    CommunityReply,
    CommunityReport,
    CommunityReportStatus,
)
from app.modules.community.schemas import (
    CommunityAuthorResponse,
    CommunityBlockCreate,
    CommunityExportResponse,
    CommunityModerationActionRequest,
    CommunityModerationQueueItem,
    CommunityModerationQueueResponse,
    CommunityOpportunityResponse,
    CommunityPostCreate,
    CommunityPostDetailResponse,
    CommunityPostListResponse,
    CommunityPostSummaryResponse,
    CommunityPostUpdate,
    CommunityPreferenceResponse,
    CommunityPreferenceUpdate,
    CommunityReplyCreate,
    CommunityReplyResponse,
    CommunityReplyUpdate,
    CommunityReportCreate,
    CommunityReportResponse,
)
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.models import (
    Opportunity,
    OpportunityStatus,
)


class CommunityService:
    """Community domain with explicit separation from private student domains."""

    NOTICE_VERSION = "phase8.community-notice.v1"
    _DISPLAY_NAME = re.compile(r"^[\w .-]{3,40}$", re.UNICODE)
    _CONTACT_OR_CREDENTIAL = re.compile(
        r"(?:\b[\w.+-]+@[\w-]+\.[\w.-]+\b|\b(?:password|passcode|otp|verification code)\b)",
        re.IGNORECASE,
    )
    _PROHIBITED = re.compile(
        r"(?:guarantee (?:admission|funding|selection)|visa advice|legal advice|"
        r"\b(?:whatsapp|telegram)\b)",
        re.IGNORECASE,
    )

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def preferences(self, user: User) -> CommunityPreferenceResponse:
        preference = self.session.get(CommunityPreference, user.id)
        return self._preference_response(preference)

    def update_preferences(
        self, user: User, payload: CommunityPreferenceUpdate
    ) -> CommunityPreferenceResponse:
        preference = self.session.get(CommunityPreference, user.id)
        if preference is None:
            if not payload.display_name:
                raise AppError("display_name_required", "Choose a community display name")
            preference = CommunityPreference(
                user_id=user.id,
                display_name=self._clean_display_name(payload.display_name, user.id),
            )
            self.session.add(preference)
        elif payload.display_name is not None:
            preference.display_name = self._clean_display_name(payload.display_name, user.id)
        if payload.consent is True:
            preference.consented_at = datetime.now(UTC)
        elif payload.consent is False:
            preference.consented_at = None
        self.session.commit()
        return self._preference_response(preference)

    def list_posts(
        self,
        user: User,
        *,
        query: str | None,
        topic: str | None,
        opportunity_id: uuid.UUID | None,
        limit: int,
        offset: int,
        bookmarked_only: bool = False,
    ) -> CommunityPostListResponse:
        blocked = select(CommunityBlock.blocked_user_id).where(CommunityBlock.user_id == user.id)
        statement = (
            select(CommunityPost)
            .where(
                CommunityPost.status == CommunityContentStatus.VISIBLE,
                CommunityPost.author_user_id.not_in(blocked),
            )
            .options(
                joinedload(CommunityPost.opportunity),
                selectinload(CommunityPost.replies),
            )
        )
        if query:
            term = f"%{query.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(CommunityPost.title).like(term),
                    func.lower(CommunityPost.body).like(term),
                )
            )
        if topic:
            statement = statement.where(CommunityPost.topic == topic)
        if opportunity_id:
            statement = statement.where(CommunityPost.opportunity_id == opportunity_id)
        if bookmarked_only:
            statement = statement.join(CommunityBookmark).where(
                CommunityBookmark.user_id == user.id
            )
        total = len(self.session.scalars(statement).all())
        rows = (
            self.session.scalars(
                statement.order_by(CommunityPost.created_at.desc()).offset(offset).limit(limit)
            )
            .unique()
            .all()
        )
        bookmarked = self._bookmarked_ids(user.id, [post.id for post in rows])
        return CommunityPostListResponse(
            posts=[self._post_summary(post, user.id, bookmarked) for post in rows],
            total=total,
            limit=limit,
            offset=offset,
            has_next=offset + len(rows) < total,
        )

    def get_post(self, post_id: uuid.UUID, user: User) -> CommunityPostDetailResponse:
        post = self._visible_post(post_id, user.id, with_replies=True)
        bookmarked = self._bookmarked_ids(user.id, [post.id])
        return CommunityPostDetailResponse(
            **self._post_summary(post, user.id, bookmarked).model_dump()
        )

    def create_post(self, payload: CommunityPostCreate, user: User) -> CommunityPostDetailResponse:
        self._require_participation(user)
        self._check_content(payload.title, payload.body)
        opportunity = (
            self._verified_opportunity(payload.opportunity_id) if payload.opportunity_id else None
        )
        post = CommunityPost(
            author_user_id=user.id,
            opportunity_id=opportunity.id if opportunity else None,
            topic=payload.topic,
            title=self._clean_text(payload.title),
            body=self._clean_text(payload.body),
        )
        self.session.add(post)
        self.session.commit()
        self.session.refresh(post)
        return CommunityPostDetailResponse(**self._post_summary(post, user.id, set()).model_dump())

    def update_post(
        self, post_id: uuid.UUID, payload: CommunityPostUpdate, user: User
    ) -> CommunityPostDetailResponse:
        self._require_participation(user)
        post = self._owned_post(post_id, user.id)
        self._check_content(payload.title, payload.body)
        post.title, post.body, post.topic = (
            self._clean_text(payload.title),
            self._clean_text(payload.body),
            payload.topic,
        )
        self.session.commit()
        return self.get_post(post.id, user)

    def delete_post(self, post_id: uuid.UUID, user: User) -> None:
        self._require_participation(user)
        post = self._owned_post(post_id, user.id)
        post.status = CommunityContentStatus.DELETED
        self.session.commit()

    def create_reply(
        self, post_id: uuid.UUID, payload: CommunityReplyCreate, user: User
    ) -> CommunityReplyResponse:
        self._require_participation(user)
        self._check_content(payload.body)
        self._visible_post(post_id, user.id)
        reply = CommunityReply(
            post_id=post_id,
            author_user_id=user.id,
            body=self._clean_text(payload.body),
        )
        self.session.add(reply)
        self.session.commit()
        return self._reply_response(reply, user.id)

    def update_reply(
        self, reply_id: uuid.UUID, payload: CommunityReplyUpdate, user: User
    ) -> CommunityReplyResponse:
        self._require_participation(user)
        reply = self._owned_reply(reply_id, user.id)
        self._check_content(payload.body)
        reply.body = self._clean_text(payload.body)
        self.session.commit()
        return self._reply_response(reply, user.id)

    def delete_reply(self, reply_id: uuid.UUID, user: User) -> None:
        self._require_participation(user)
        reply = self._owned_reply(reply_id, user.id)
        reply.status = CommunityContentStatus.DELETED
        self.session.commit()

    def bookmark(self, post_id: uuid.UUID, user: User) -> None:
        self._require_participation(user)
        self._visible_post(post_id, user.id)
        exists = self.session.scalar(
            select(CommunityBookmark).where(
                CommunityBookmark.user_id == user.id,
                CommunityBookmark.post_id == post_id,
            )
        )
        if exists is None:
            self.session.add(CommunityBookmark(user_id=user.id, post_id=post_id))
            self.session.commit()

    def unbookmark(self, post_id: uuid.UUID, user: User) -> None:
        bookmark = self.session.scalar(
            select(CommunityBookmark).where(
                CommunityBookmark.user_id == user.id,
                CommunityBookmark.post_id == post_id,
            )
        )
        if bookmark:
            self.session.delete(bookmark)
            self.session.commit()

    def block(self, payload: CommunityBlockCreate, user: User) -> None:
        self._require_participation(user)
        if payload.user_id == user.id:
            raise AppError("invalid_block", "You cannot block yourself")
        if self.session.get(User, payload.user_id) is None:
            raise AppError("community_member_not_found", "Community member not found", 404)
        exists = self.session.scalar(
            select(CommunityBlock).where(
                CommunityBlock.user_id == user.id,
                CommunityBlock.blocked_user_id == payload.user_id,
            )
        )
        if exists is None:
            self.session.add(CommunityBlock(user_id=user.id, blocked_user_id=payload.user_id))
            self.session.commit()

    def unblock(self, blocked_user_id: uuid.UUID, user: User) -> None:
        block = self.session.scalar(
            select(CommunityBlock).where(
                CommunityBlock.user_id == user.id,
                CommunityBlock.blocked_user_id == blocked_user_id,
            )
        )
        if block:
            self.session.delete(block)
            self.session.commit()

    def report(self, payload: CommunityReportCreate, user: User) -> CommunityReportResponse:
        self._require_participation(user)
        if payload.post_id:
            target = self._visible_post(payload.post_id, user.id)
            if target.author_user_id == user.id:
                raise AppError("invalid_report", "You cannot report your own content")
        else:
            target = self.session.get(CommunityReply, payload.reply_id)
            if target is None or target.status is not CommunityContentStatus.VISIBLE:
                raise AppError(
                    "community_content_not_found",
                    "Community content not found",
                    404,
                )
            if target.author_user_id == user.id:
                raise AppError("invalid_report", "You cannot report your own content")
        existing = self.session.scalar(
            select(CommunityReport).where(
                CommunityReport.reporter_user_id == user.id,
                CommunityReport.post_id == payload.post_id,
                CommunityReport.reply_id == payload.reply_id,
            )
        )
        if existing:
            raise ConflictError(
                "community_report_exists",
                "You have already reported this content",
            )
        report = CommunityReport(
            reporter_user_id=user.id,
            post_id=payload.post_id,
            reply_id=payload.reply_id,
            reason=payload.reason,
            detail=self._clean_text(payload.detail) if payload.detail else None,
        )
        self.session.add(report)
        self.session.commit()
        return CommunityReportResponse.model_validate(report)

    def moderation_queue(self, *, limit: int, offset: int) -> CommunityModerationQueueResponse:
        statement = select(CommunityReport).where(
            CommunityReport.status == CommunityReportStatus.OPEN
        )
        total = len(self.session.scalars(statement).all())
        reports = self.session.scalars(
            statement.order_by(CommunityReport.created_at.asc()).offset(offset).limit(limit)
        ).all()
        items: list[CommunityModerationQueueItem] = []
        for report in reports:
            content = (
                self.session.get(CommunityPost, report.post_id)
                if report.post_id
                else self.session.get(CommunityReply, report.reply_id)
            )
            if content is None:
                continue
            items.append(
                CommunityModerationQueueItem(
                    report=CommunityReportResponse.model_validate(report),
                    content_type="post" if report.post_id else "reply",
                    content_id=content.id,
                    content_preview=content.title if report.post_id else content.body[:180],
                    author=self._author(content.author_user_id),
                    status=content.status,
                )
            )
        return CommunityModerationQueueResponse(
            reports=items,
            total=total,
            limit=limit,
            offset=offset,
            has_next=offset + len(reports) < total,
        )

    def moderate(self, payload: CommunityModerationActionRequest, moderator: User) -> None:
        if moderator.role is not UserRole.ADMIN:
            raise AppError(
                "forbidden",
                "You do not have permission to perform this action",
                403,
            )
        target_type, target_id = "", ""
        if payload.action in {
            CommunityModerationAction.HIDE,
            CommunityModerationAction.RESTORE,
        }:
            content = (
                self.session.get(CommunityPost, payload.post_id)
                if payload.post_id
                else self.session.get(CommunityReply, payload.reply_id)
            )
            if content is None:
                raise AppError(
                    "community_content_not_found",
                    "Community content not found",
                    404,
                )
            content.status = (
                CommunityContentStatus.HIDDEN
                if payload.action is CommunityModerationAction.HIDE
                else CommunityContentStatus.VISIBLE
            )
            target_type, target_id = (
                ("post" if payload.post_id else "reply"),
                str(content.id),
            )
        elif payload.action in {
            CommunityModerationAction.SUSPEND,
            CommunityModerationAction.REINSTATE,
        }:
            preference = self.session.get(CommunityPreference, payload.user_id)
            if preference is None:
                raise AppError(
                    "community_member_not_found",
                    "Community member not found",
                    404,
                )
            preference.suspended_at = (
                datetime.now(UTC) if payload.action is CommunityModerationAction.SUSPEND else None
            )
            preference.suspension_reason = (
                payload.reason if payload.action is CommunityModerationAction.SUSPEND else None
            )
            target_type, target_id = "user", str(preference.user_id)
        else:
            report = self.session.get(CommunityReport, payload.report_id)
            if report is None:
                raise AppError(
                    "community_report_not_found",
                    "Community report not found",
                    404,
                )
            report.status, report.resolved_at, report.resolved_by_user_id = (
                CommunityReportStatus.RESOLVED,
                datetime.now(UTC),
                moderator.id,
            )
            target_type, target_id = "report", str(report.id)
        self.session.add(
            CommunityModerationRecord(
                moderator_user_id=moderator.id,
                action=payload.action,
                target_type=target_type,
                target_id=target_id,
                reason=payload.reason,
            )
        )
        self.session.add(
            AuditLog(
                actor_user_id=moderator.id,
                action=f"community.{payload.action.value}",
                entity_type=target_type,
                entity_id=target_id,
                metadata_json={"phase": "community"},
            )
        )
        self.session.commit()

    def export_data(self, user: User) -> CommunityExportResponse:
        posts = self.session.scalars(
            select(CommunityPost)
            .where(CommunityPost.author_user_id == user.id)
            .options(
                selectinload(CommunityPost.replies),
                joinedload(CommunityPost.opportunity),
            )
        ).all()
        reports = self.session.scalars(
            select(CommunityReport).where(CommunityReport.reporter_user_id == user.id)
        ).all()
        return CommunityExportResponse(
            preferences=self.preferences(user),
            posts=[
                CommunityPostDetailResponse(**self._post_summary(post, user.id, set()).model_dump())
                for post in posts
            ],
            reports=[CommunityReportResponse.model_validate(report) for report in reports],
        )

    def delete_data(self, user: User) -> None:
        self.session.execute(delete(CommunityBookmark).where(CommunityBookmark.user_id == user.id))
        self.session.execute(
            delete(CommunityBlock).where(
                or_(
                    CommunityBlock.user_id == user.id,
                    CommunityBlock.blocked_user_id == user.id,
                )
            )
        )
        self.session.execute(
            delete(CommunityReport).where(CommunityReport.reporter_user_id == user.id)
        )
        self.session.execute(delete(CommunityReply).where(CommunityReply.author_user_id == user.id))
        self.session.execute(delete(CommunityPost).where(CommunityPost.author_user_id == user.id))
        preference = self.session.get(CommunityPreference, user.id)
        if preference:
            self.session.delete(preference)
        self.session.commit()

    def _require_participation(self, user: User) -> CommunityPreference:
        if self.settings.env == "production" and user.email_verified_at is None:
            raise AppError(
                "community_email_verification_required",
                "Verify your email before participating",
                403,
            )
        preference = self.session.get(CommunityPreference, user.id)
        if preference is None or preference.consented_at is None:
            raise AppError(
                "community_consent_required",
                "Accept the community notice before participating",
                403,
            )
        if preference.suspended_at is not None:
            raise AppError(
                "community_participation_suspended",
                "Your community participation is suspended",
                403,
            )
        return preference

    def _verified_opportunity(self, opportunity_id: uuid.UUID) -> Opportunity:
        opportunity = self.session.scalar(
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .options(selectinload(Opportunity.sources))
        )
        if opportunity is None or opportunity.status is not OpportunityStatus.ACTIVE:
            raise AppError(
                "community_opportunity_not_found",
                "Verified scholarship not found",
                404,
            )
        if EvidencePolicy.select_current_official_source(opportunity.sources) is None:
            raise AppError(
                "community_opportunity_not_found",
                "Verified scholarship not found",
                404,
            )
        return opportunity

    def _visible_post(
        self,
        post_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        with_replies: bool = False,
    ) -> CommunityPost:
        statement = (
            select(CommunityPost)
            .where(
                CommunityPost.id == post_id,
                CommunityPost.status == CommunityContentStatus.VISIBLE,
            )
            .options(joinedload(CommunityPost.opportunity))
        )
        if with_replies:
            statement = statement.options(selectinload(CommunityPost.replies))
        post = self.session.scalar(statement)
        if post is None or post.author_user_id in self._blocked_ids(user_id):
            raise AppError("community_post_not_found", "Community post not found", 404)
        return post

    def _owned_post(self, post_id: uuid.UUID, user_id: uuid.UUID) -> CommunityPost:
        post = self.session.scalar(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.author_user_id == user_id,
                CommunityPost.status == CommunityContentStatus.VISIBLE,
            )
        )
        if post is None:
            raise AppError("community_post_not_found", "Community post not found", 404)
        return post

    def _owned_reply(self, reply_id: uuid.UUID, user_id: uuid.UUID) -> CommunityReply:
        reply = self.session.scalar(
            select(CommunityReply).where(
                CommunityReply.id == reply_id,
                CommunityReply.author_user_id == user_id,
                CommunityReply.status == CommunityContentStatus.VISIBLE,
            )
        )
        if reply is None:
            raise AppError("community_reply_not_found", "Community reply not found", 404)
        return reply

    def _post_summary(
        self,
        post: CommunityPost,
        user_id: uuid.UUID,
        bookmarked: set[uuid.UUID],
    ) -> CommunityPostSummaryResponse:
        replies = [
            self._reply_response(reply, user_id)
            for reply in post.replies
            if reply.status is CommunityContentStatus.VISIBLE
            and reply.author_user_id not in self._blocked_ids(user_id)
        ]
        return CommunityPostSummaryResponse(
            id=post.id,
            topic=post.topic,
            title=post.title,
            body=post.body,
            author=self._author(post.author_user_id),
            opportunity=CommunityOpportunityResponse(
                id=post.opportunity.id, name=post.opportunity.name
            )
            if post.opportunity
            else None,
            reply_count=sum(
                reply.status is CommunityContentStatus.VISIBLE for reply in post.replies
            ),
            created_at=post.created_at,
            updated_at=post.updated_at,
            is_owner=post.author_user_id == user_id,
            is_bookmarked=post.id in bookmarked,
            replies=replies,
        )

    def _reply_response(self, reply: CommunityReply, user_id: uuid.UUID) -> CommunityReplyResponse:
        return CommunityReplyResponse(
            id=reply.id,
            body=reply.body,
            author=self._author(reply.author_user_id),
            created_at=reply.created_at,
            updated_at=reply.updated_at,
            is_owner=reply.author_user_id == user_id,
        )

    def _author(self, user_id: uuid.UUID) -> CommunityAuthorResponse:
        preference = self.session.get(CommunityPreference, user_id)
        # The fallback protects legacy content if a preference was later deleted.
        return CommunityAuthorResponse(
            id=user_id,
            display_name=preference.display_name if preference else "Community member",
        )

    def _preference_response(
        self, preference: CommunityPreference | None
    ) -> CommunityPreferenceResponse:
        return CommunityPreferenceResponse(
            display_name=preference.display_name if preference else None,
            consented=bool(preference and preference.consented_at),
            suspended=bool(preference and preference.suspended_at),
            notice_version=self.NOTICE_VERSION,
        )

    def _bookmarked_ids(self, user_id: uuid.UUID, post_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not post_ids:
            return set()
        return set(
            self.session.scalars(
                select(CommunityBookmark.post_id).where(
                    CommunityBookmark.user_id == user_id,
                    CommunityBookmark.post_id.in_(post_ids),
                )
            ).all()
        )

    def _blocked_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        return set(
            self.session.scalars(
                select(CommunityBlock.blocked_user_id).where(CommunityBlock.user_id == user_id)
            ).all()
        )

    def _clean_display_name(self, value: str, user_id: uuid.UUID) -> str:
        value = self._clean_text(value)
        if not self._DISPLAY_NAME.fullmatch(value):
            raise AppError(
                "invalid_display_name",
                "Use 3-40 letters, numbers, spaces, dots, hyphens, or underscores",
            )
        duplicate = self.session.scalar(
            select(CommunityPreference).where(
                func.lower(CommunityPreference.display_name) == value.lower()
            )
        )
        if duplicate and duplicate.user_id != user_id:
            raise ConflictError(
                "community_display_name_taken",
                "That community display name is already in use",
            )
        return value

    def _check_content(self, *values: str) -> None:
        text = " ".join(values)
        if self._CONTACT_OR_CREDENTIAL.search(text):
            raise AppError(
                "community_content_rejected",
                "Do not share contact details or credentials in community content",
            )
        if self._PROHIBITED.search(text):
            raise AppError(
                "community_content_rejected",
                "This community cannot provide guarantees or legal or visa advice",
            )

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.strip().split())
