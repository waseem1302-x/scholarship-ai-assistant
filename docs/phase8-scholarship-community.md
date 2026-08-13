# Phase 8 — Scholarship-only community

## Product decision and scope

Phase 8 adds a moderated, authenticated discussion space for practical
scholarship-application support. It is not a general social network and it is
not an alternative source of official scholarship facts. The verified catalogue
remains the only product authority for factual opportunity information.

The community is deliberately limited to a small, safe first release:

- A student can browse a paginated public-to-members feed, search discussions,
  and filter them by a verified scholarship and a structured discussion topic.
- A student can create, edit, or delete their own post; add or delete their own
  reply; and bookmark posts. Posts and replies are visible only after a basic
  automated safety check and are subject to moderation.
- A student can report harmful, off-topic, or misleading content and block an
  author. Blocking hides that author's content from the blocker's feed without
  disclosing the block to the blocked user.
- An administrator can inspect a report queue, hide or restore content,
  resolve reports, and suspend or reinstate community participation. Each
  moderator action produces a minimal, content-free audit event.

## Explicit requirements

| Requirement | Release rule |
| --- | --- |
| Scholarship-centred discussion | Every post has one controlled topic and may reference one existing, publicly verified scholarship. There are no free-form groups, direct messages, follower graphs, or general feed algorithms. |
| Clear evidence boundary | Community content is labelled as member experience, not official advice. A scholarship reference renders a link to the verified catalogue. Posts do not change catalogue data or assistant answers. |
| Privacy by design | Community responses expose a stable pseudonymous display name, never an email address, profile, application, reminder, assistant, or Document Lab data. Community export/delete operates only on community records. |
| Safe participation | Require authentication, email verification in production, consent to a community notice, bounded plain-text input, per-user/IP write limits, reports, blocks, and server-side content policy checks. |
| Professional moderation | Moderators receive reports, can hide/restore posts or replies, resolve reports with controlled dispositions, and suspend participation. Actions are idempotent and auditable without storing body text in audit metadata. |
| Accessible user experience | Use semantic forms, visible labels, keyboard-operable controls, live success/error status, understandable empty states, and no raw HTML injection. |
| Data integrity | Use append-only report/moderation records, owner-scoped writes, pagination, foreign keys, unique bookmarks/blocks, and transactional create/update operations. |
| Operationally safe | The in-process limiter remains appropriate only for a single instance; Phase 9 must replace it with a shared limiter before horizontal scaling. |

## Content policy

Permitted content is practical, scholarship-related experience and questions.
It must not include another person's personal information, uploaded documents,
credentials, contact details, harassment, discriminatory abuse, solicitation,
or claims that a scholarship outcome is guaranteed. Members are asked to link
to official evidence when correcting a factual statement. The first release
rejects obvious credential/contact details and high-risk advisory or guarantee
phrases; moderation remains the final decision maker.

## Roles and visibility

- A signed-in student may read visible content, create and manage their own
  content, report, block, and bookmark.
- An administrator is also a community moderator. Administrative actions use
  the existing administrator step-up control in production.
- Hidden or deleted content is omitted from all student-facing queries.
- A suspended participant may read visible content but cannot create, edit,
  reply, report, block, or bookmark. They receive a clear suspension message.

## Deliberate non-goals

- Direct messages, follower lists, live chat, notifications, image/file uploads,
  public profile pages, reputation scores, success-story claims, or external
  social logins.
- Automated fact verification, automated bans, recommendation ranking based on
  sensitive personal data, or using community text in the AI assistant.
- Exposure of private application data, profile contents, Document Lab drafts,
  assistant history, reminders, or account email addresses.

## Acceptance criteria

1. A verified student can create a scholarship-linked post, reply, edit/delete
   their own material, and bookmark it; other students cannot edit or delete it.
2. A post tied to an inactive, unverified, or unknown scholarship is rejected.
3. A blocked author is absent from the blocker's list, search, and detail
   responses; other students' visibility is unaffected.
4. Reported content reaches an admin-only queue. Hiding content removes it from
   student queries; restoration returns it if no other hide action applies.
5. A suspended user cannot write. Admin actions require the existing step-up
   protection in production and create safe audit entries.
6. Responses never contain private domain fields or an author email address.
7. Community deletion removes only the caller's authored content, bookmarks,
   blocks, reports, and consent/profile data; it must not touch applications,
   assistant history, or Document Lab data.
8. API, migration, frontend-unit, and browser-style journeys cover these
   boundaries; linting, type checks, and migration rehearsal pass.

## API outline

All routes are below `/api/v1/community` and require a student or admin session:

```text
GET    /posts                         list/search/filter visible posts
POST   /posts                         create post
GET    /posts/{id}                    post and visible replies
PATCH  /posts/{id}                    author edits own post
DELETE /posts/{id}                    author soft-deletes own post
POST   /posts/{id}/replies            create reply
PATCH  /replies/{id}                  author edits own reply
DELETE /replies/{id}                  author soft-deletes own reply
POST   /posts/{id}/bookmarks          bookmark
DELETE /posts/{id}/bookmarks          remove bookmark
GET    /bookmarks                     list own bookmarks
POST   /blocks                        block author
DELETE /blocks/{user_id}              unblock author
POST   /reports                       report a post or reply
GET    /preferences                   read consent/display name/participation status
PUT    /preferences                   grant/revoke consent and set display name
GET    /export                        export only caller's community records
DELETE /data                          delete only caller's community records

GET    /admin/reports                 moderation queue
POST   /admin/moderation-actions      hide/restore content, resolve reports, suspend/reinstate
```

## Delivery order

1. Schema/migration, models, safety configuration, repository, service, and
   API tests.
2. React feed/detail/composer/bookmark/report/block and moderator queue.
3. Browser and integration verification, documentation, and a Docker migration
   rehearsal against the existing Compose project.
