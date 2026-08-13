import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
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
    _OBFUSCATED_CONTACT = re.compile(
        r"(?:\b[\w.+-]+\s*(?:@|\bat\b|\[at\]|\(at\))\s*[\w-]+"
        r"\s*(?:\.|\bdot\b|\[dot\]|\(dot\))\s*[\w.-]+\b|"
        r"\b(?:discord|instagram|insta|snapchat|telegram|whatsapp|wechat|line)\s*[:@]\s*\w+|"
        r"\b(?:dm|direct message|message me|contact me)\b|"
        r"\b(?:\+?\d[\d .()_-]{7,}\d)\b)",
        re.IGNORECASE,
    )
    _LINK_OR_SHORTENER = re.compile(
        r"(?:https?://|www\.|bit\.ly|tinyurl\.com|t\.me/|discord\.gg/)",
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
            preference.display_name_normalized = preference.display_name.casefold()
            self.session.add(preference)
        elif payload.display_name is not None:
            preference.display_name = self._clean_display_name(payload.display_name, user.id)
            preference.display_name_normalized = preference.display_name.casefold()
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
        blocked_ids = self._blocked_ids(user.id)
        statement = (
            select(CommunityPost)
            .where(
                CommunityPost.status == CommunityContentStatus.VISIBLE,
            )
        )
        if blocked_ids:
            statement = statement.where(CommunityPost.author_user_id.not_in(blocked_ids))
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
        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = (
            self.session.scalars(
                statement.options(
                    joinedload(CommunityPost.opportunity),
                    selectinload(CommunityPost.replies),
                )
                .order_by(CommunityPost.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .unique()
            .all()
        )
        bookmarked = self._bookmarked_ids(user.id, [post.id for post in rows])
        authors = self._authors_for(self._author_ids_for_posts(rows, blocked_ids))
        return CommunityPostListResponse(
            posts=[
                self._post_summary(
                    post,
                    user.id,
                    bookmarked,
                    blocked_ids=blocked_ids,
                    authors=authors,
                )
                for post in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
            has_next=offset + len(rows) < total,
        )

    def get_post(self, post_id: uuid.UUID, user: User) -> CommunityPostDetailResponse:
        post = self._visible_post(post_id, user.id, with_replies=True)
        bookmarked = self._bookmarked_ids(user.id, [post.id])
        blocked_ids = self._blocked_ids(user.id)
        authors = self._authors_for(self._author_ids_for_posts([post], blocked_ids))
        return CommunityPostDetailResponse(
            **self._post_summary(
                post,
                user.id,
                bookmarked,
                blocked_ids=blocked_ids,
                authors=authors,
            ).model_dump()
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
        target_user_id = self._community_user_id(payload.user_id)
        if target_user_id == user.id:
            raise AppError("invalid_block", "You cannot block yourself")
        exists = self.session.scalar(
            select(CommunityBlock).where(
                CommunityBlock.user_id == user.id,
                CommunityBlock.blocked_user_id == target_user_id,
            )
        )
        if exists is None:
            self.session.add(CommunityBlock(user_id=user.id, blocked_user_id=target_user_id))
            self.session.commit()

    def unblock(self, blocked_public_id: uuid.UUID, user: User) -> None:
        blocked_user_id = self._community_user_id(blocked_public_id)
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
        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
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
        reported_post_ids = select(CommunityReport.post_id).where(
            CommunityReport.post_id.is_not(None)
        )
        reported_reply_ids = select(CommunityReport.reply_id).where(
            CommunityReport.reply_id.is_not(None)
        )
        posts_with_reported_replies = select(CommunityReply.post_id).where(
            CommunityReply.id.in_(reported_reply_ids)
        )
        self.session.execute(
            update(CommunityReport)
            .where(CommunityReport.reporter_user_id == user.id)
            .values(detail=None)
        )
        self.session.execute(
            update(CommunityReply)
            .where(
                CommunityReply.author_user_id == user.id,
                CommunityReply.id.in_(reported_reply_ids),
            )
            .values(body="[deleted by member]", status=CommunityContentStatus.HIDDEN)
        )
        self.session.execute(
            delete(CommunityReply).where(
                CommunityReply.author_user_id == user.id,
                CommunityReply.id.not_in(reported_reply_ids),
            )
        )
        self.session.execute(
            update(CommunityPost)
            .where(
                CommunityPost.author_user_id == user.id,
                or_(
                    CommunityPost.id.in_(reported_post_ids),
                    CommunityPost.id.in_(posts_with_reported_replies),
                ),
            )
            .values(
                title="[deleted by member]",
                body="[deleted by member]",
                status=CommunityContentStatus.HIDDEN,
            )
        )
        self.session.execute(
            delete(CommunityPost).where(
                CommunityPost.author_user_id == user.id,
                CommunityPost.id.not_in(reported_post_ids),
                CommunityPost.id.not_in(posts_with_reported_replies),
            )
        )
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
        *,
        blocked_ids: set[uuid.UUID] | None = None,
        authors: dict[uuid.UUID, CommunityAuthorResponse] | None = None,
    ) -> CommunityPostSummaryResponse:
        blocked_ids = blocked_ids if blocked_ids is not None else self._blocked_ids(user_id)
        authors = authors or self._authors_for(self._author_ids_for_posts([post], blocked_ids))
        replies = [
            self._reply_response(reply, user_id, authors)
            for reply in post.replies
            if reply.status is CommunityContentStatus.VISIBLE
            and reply.author_user_id not in blocked_ids
        ]
        total_reply_count = sum(
            reply.status is CommunityContentStatus.VISIBLE for reply in post.replies
        )
        return CommunityPostSummaryResponse(
            id=post.id,
            topic=post.topic,
            title=post.title,
            body=post.body,
            author=authors[post.author_user_id],
            opportunity=CommunityOpportunityResponse(
                id=post.opportunity.id, name=post.opportunity.name
            )
            if post.opportunity
            else None,
            reply_count=total_reply_count,
            visible_reply_count=len(replies),
            created_at=post.created_at,
            updated_at=post.updated_at,
            is_owner=post.author_user_id == user_id,
            is_bookmarked=post.id in bookmarked,
            replies=replies,
        )

    def _reply_response(
        self,
        reply: CommunityReply,
        user_id: uuid.UUID,
        authors: dict[uuid.UUID, CommunityAuthorResponse] | None = None,
    ) -> CommunityReplyResponse:
        authors = authors or self._authors_for({reply.author_user_id})
        return CommunityReplyResponse(
            id=reply.id,
            body=reply.body,
            author=authors[reply.author_user_id],
            created_at=reply.created_at,
            updated_at=reply.updated_at,
            is_owner=reply.author_user_id == user_id,
        )

    def _author(self, user_id: uuid.UUID) -> CommunityAuthorResponse:
        return self._authors_for({user_id})[user_id]

    def _authors_for(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, CommunityAuthorResponse]:
        if not user_ids:
            return {}
        preferences = {
            preference.user_id: preference
            for preference in self.session.scalars(
                select(CommunityPreference).where(CommunityPreference.user_id.in_(user_ids))
            ).all()
        }
        return {
            user_id: CommunityAuthorResponse(
                id=preferences[user_id].public_id
                if user_id in preferences
                else uuid.uuid5(uuid.NAMESPACE_URL, f"community:{user_id}"),
                display_name=preferences[user_id].display_name
                if user_id in preferences
                else "Community member",
            )
            for user_id in user_ids
        }

    @staticmethod
    def _author_ids_for_posts(
        posts: list[CommunityPost], blocked_ids: set[uuid.UUID]
    ) -> set[uuid.UUID]:
        ids = {post.author_user_id for post in posts}
        for post in posts:
            ids.update(
                reply.author_user_id
                for reply in post.replies
                if reply.status is CommunityContentStatus.VISIBLE
                and reply.author_user_id not in blocked_ids
            )
        return ids

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
        outgoing = select(CommunityBlock.blocked_user_id).where(CommunityBlock.user_id == user_id)
        incoming = select(CommunityBlock.user_id).where(CommunityBlock.blocked_user_id == user_id)
        return set(self.session.scalars(outgoing).all()) | set(
            self.session.scalars(incoming).all()
        )

    def _community_user_id(self, public_id: uuid.UUID) -> uuid.UUID:
        preference = self.session.scalar(
            select(CommunityPreference).where(CommunityPreference.public_id == public_id)
        )
        if preference is None:
            raise AppError("community_member_not_found", "Community member not found", 404)
        return preference.user_id

    def _clean_display_name(self, value: str, user_id: uuid.UUID) -> str:
        value = self._clean_text(value)
        if not self._DISPLAY_NAME.fullmatch(value):
            raise AppError(
                "invalid_display_name",
                "Use 3-40 letters, numbers, spaces, dots, hyphens, or underscores",
            )
        duplicate = self.session.scalar(
            select(CommunityPreference).where(
                CommunityPreference.display_name_normalized == value.casefold()
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
        score = 0
        if self._CONTACT_OR_CREDENTIAL.search(text):
            score += 5
        if self._OBFUSCATED_CONTACT.search(text):
            score += 5
        if self._LINK_OR_SHORTENER.search(text):
            score += 2
        if score >= 5:
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
