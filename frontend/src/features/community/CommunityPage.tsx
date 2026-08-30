import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { ApiError, apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";

type Author = { id: string; display_name: string };
type Reply = { id: string; body: string; author: Author; is_owner: boolean; created_at: string };
type Post = {
  id: string;
  title: string;
  body: string;
  topic: string;
  author: Author;
  is_owner: boolean;
  is_bookmarked: boolean;
  reply_count: number;
  created_at: string;
  opportunity: { id: string; name: string } | null;
  replies?: Reply[];
};
type Feed = { posts: Post[]; total: number; has_next: boolean };
type Preferences = { display_name: string | null; consented: boolean; suspended: boolean; notice_version: string };
type Report = {
  id: string;
  content_type: "post" | "reply";
  content_id: string;
  content_preview: string;
  author: Author;
  status: string;
  report: { id: string; reason: string; detail: string | null };
};
type ReportQueue = { reports: Report[] };

const topics = [
  { id: "all", label: "🔥 For You" },
  { id: "question", label: "❓ Questions" },
  { id: "application_process", label: "✍️ Essay Lab" },
  { id: "interview", label: "🎙️ Interview Intel" },
  { id: "documents", label: "📁 Documents" },
  { id: "timeline", label: "⏰ Deadlines & Results" },
  { id: "official_source_update", label: "📌 Official Notices" },
];

function labelTopic(value: string) {
  return value.replaceAll("_", " ");
}

function failure(error: unknown) {
  return error instanceof ApiError ? error.message : "We could not complete that community action.";
}

function authorInitials(name: string): string {
  const parts = name.trim().split(" ");
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${Math.max(1, mins)}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function CommunityPage() {
  const { user, isRestoring } = useAuth();
  const [searchParams] = useSearchParams();
  const opportunityId = searchParams.get("opportunity") ?? undefined;

  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [activeTopic, setActiveTopic] = useState<string>("all");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [topic, setTopic] = useState("question");
  const [displayName, setDisplayName] = useState("");
  const [replyText, setReplyText] = useState<Record<string, string>>({});
  const [expandedReplies, setExpandedReplies] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([]);

  const canParticipate = Boolean(preferences?.consented && !preferences.suspended);

  async function load(signal?: AbortSignal) {
    try {
      const [nextPreferences, nextFeed] = await Promise.all([
        apiClient.request<Preferences>("/community/preferences", { signal }),
        apiClient.request<Feed>(`/community/posts${query ? `?q=${encodeURIComponent(query)}` : ""}`, { signal }),
      ]);
      setPreferences(nextPreferences);
      setDisplayName(nextPreferences.display_name ?? "");
      setFeed(nextFeed);
      if (user?.role === "admin") {
        setReports((await apiClient.request<ReportQueue>("/community/admin/reports", { signal })).reports);
      }
    } catch (requestError) {
      if (!signal?.aborted) setError(failure(requestError));
    }
  }

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [user]);

  if (!isRestoring && !user) return <Navigate replace to="/auth" />;
  if (!user) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session…</main>;

  async function participate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiClient.request("/community/preferences", {
        method: "PUT",
        body: JSON.stringify({ display_name: displayName, consent: true }),
      });
      setNotice("You can now participate using your community display name.");
      await load();
    } catch (requestError) {
      setError(failure(requestError));
    }
  }

  async function publish(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiClient.request("/community/posts", {
        method: "POST",
        body: JSON.stringify({ title, body, topic, opportunity_id: opportunityId }),
      });
      setTitle("");
      setBody("");
      setNotice("Your post is now visible to the community.");
      await load();
    } catch (requestError) {
      setError(failure(requestError));
    }
  }

  async function reply(postId: string) {
    const next = replyText[postId]?.trim();
    if (!next) return;
    try {
      await apiClient.request(`/community/posts/${postId}/replies`, {
        method: "POST",
        body: JSON.stringify({ body: next }),
      });
      setReplyText((prev) => ({ ...prev, [postId]: "" }));
      setExpandedReplies((prev) => ({ ...prev, [postId]: true }));
      await load();
    } catch (requestError) {
      setError(failure(requestError));
    }
  }

  async function action(path: string, method: "POST" | "DELETE", reqBody?: object) {
    try {
      await apiClient.request(path, { method, body: reqBody ? JSON.stringify(reqBody) : undefined });
      await load();
    } catch (requestError) {
      setError(failure(requestError));
    }
  }

  async function moderate(actionType: string, item: Report) {
    try {
      await apiClient.request("/community/admin/moderation-actions", {
        method: "POST",
        body: JSON.stringify(
          actionType === "resolve_report"
            ? { action: actionType, report_id: item.report.id }
            : { action: actionType, [`${item.content_type}_id`]: item.content_id, reason: "Moderator action" },
        ),
      });
      await load();
    } catch (requestError) {
      setError(failure(requestError));
    }
  }

  const filteredPosts = useMemo(() => {
    if (!feed?.posts) return [];
    if (activeTopic === "all") return feed.posts;
    return feed.posts.filter((p) => p.topic === activeTopic);
  }, [feed, activeTopic]);

  return (
    <main className="community-feed-page">
      <div className="community-feed-shell">
        <section className="community-stream-column">
          <div className="community-stream-header">
            <div>
              <p className="eyebrow">Scholarship-Only Community</p>
              <h1>Applicant Discussions & Intel</h1>
              <p className="lead">
                Peer advice and interview preparation — confirmed by official statutory source evidence.
              </p>
            </div>
            <form
              className="community-search-bar"
              onSubmit={(event) => {
                event.preventDefault();
                void load();
              }}
            >
              <label className="sr-only" htmlFor="community-search">Search discussions</label>
              <input
                id="community-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search topics, essays, advice..."
              />
              <button className="button button-quiet" type="submit">Search</button>
            </form>
          </div>

          {error ? <div className="form-error" role="alert">{error}</div> : null}
          {notice ? <div className="form-success" role="status">{notice}</div> : null}

          <div className="community-filter-rail no-scrollbar" role="tablist" aria-label="Filter discussions by topic">
            {topics.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`filter-capsule ${activeTopic === t.id ? "active" : ""}`}
                onClick={() => setActiveTopic(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {!preferences?.consented ? (
            <form className="clean-feed-card community-onboarding-card" onSubmit={participate}>
              <h2>Choose how you appear to members</h2>
              <p>Your display name is visible on posts. Email, private documents, and assistant sessions remain 100% private.</p>
              <div className="onboarding-form-row">
                <label>
                  <span>Community Display Name</span>
                  <input
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    minLength={3}
                    maxLength={40}
                    placeholder="e.g. Scholar_Alex"
                    required
                  />
                </label>
                <label className="checkbox-consent-label">
                  <input type="checkbox" required />
                  <span>I agree to keep discussion scholarship-related and report unsafe content.</span>
                </label>
                <button className="button button-primary" type="submit">Join Community</button>
              </div>
            </form>
          ) : preferences.suspended ? (
            <div className="clean-feed-card community-suspended-card" role="alert">
              <h2>Participation is suspended</h2>
              <p>You can read visible discussions, but posting and commenting are currently suspended.</p>
            </div>
          ) : (
            <form className="clean-feed-card community-composer-card" onSubmit={publish}>
              <div className="composer-top-row">
                <div className="scholar-avatar avatar-uk">
                  {authorInitials(displayName || user.email || "WM")}
                </div>
                <div className="composer-input-stack">
                  <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Discussion title or question (e.g. Chevening Leadership Essay structure)..."
                    minLength={4}
                    maxLength={160}
                    required
                    className="composer-title-input"
                  />
                  <textarea
                    value={body}
                    onChange={(event) => setBody(event.target.value)}
                    placeholder="What advice, interview pointer, or specific question would help fellow applicants?"
                    minLength={10}
                    maxLength={6000}
                    required
                    className="composer-body-textarea"
                  />
                </div>
              </div>

              <div className="composer-bottom-bar">
                <div className="composer-selectors">
                  <label className="composer-topic-select">
                    <span className="sr-only">Topic</span>
                    <select value={topic} onChange={(event) => setTopic(event.target.value)}>
                      {topics.filter((t) => t.id !== "all").map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {opportunityId ? (
                    <span className="composer-linked-badge">
                      <span>🏛️ Linked to opportunity</span>
                    </span>
                  ) : null}
                </div>
                <button className="button button-primary" type="submit">
                  Publish Discussion
                </button>
              </div>
            </form>
          )}

          <div className="community-posts-stream">
            {!feed ? (
              <div className="clean-feed-card loading-card" aria-live="polite">
                <p>Loading community stream…</p>
              </div>
            ) : !filteredPosts.length ? (
              <div className="clean-feed-card empty-feed-card">
                <h2>No discussions in this topic yet</h2>
                <p>Be the first to share an application framework, interview debrief, or ask a question.</p>
              </div>
            ) : (
              filteredPosts.map((post) => {
                const initials = authorInitials(post.author.display_name);
                const isRepliesOpen = expandedReplies[post.id] ?? false;

                return (
                  <article className="clean-feed-card community-post-item" key={post.id}>
                    <div className="post-header-row">
                      <div className="post-author-group">
                        <div className="scholar-avatar avatar-uk">{initials}</div>
                        <div>
                          <div className="post-author-line">
                            <strong>{post.author.display_name}</strong>
                            <span className="scholar-badge">
                              <span>✓</span> Member
                            </span>
                            <span className="post-time-tag">· {formatRelativeTime(post.created_at)}</span>
                          </div>
                          <span className="post-topic-tag">{labelTopic(post.topic)}</span>
                        </div>
                      </div>

                      {canParticipate && !post.is_owner ? (
                        <div className="post-menu-actions">
                          <button
                            type="button"
                            className="text-link-quiet"
                            title="Block author"
                            onClick={() => void action("/community/blocks", "POST", { user_id: post.author.id })}
                          >
                            Block
                          </button>
                          <button
                            type="button"
                            className="text-link-quiet"
                            title="Report post"
                            onClick={() =>
                              void action("/community/reports", "POST", {
                                post_id: post.id,
                                reason: "misleading",
                                detail: "Please review this community content.",
                              })
                            }
                          >
                            Report
                          </button>
                        </div>
                      ) : post.is_owner ? (
                        <button
                          type="button"
                          className="text-link-quiet text-link-danger"
                          onClick={() => void action(`/community/posts/${post.id}`, "DELETE")}
                        >
                          Delete
                        </button>
                      ) : null}
                    </div>

                    {post.opportunity ? (
                      <div>
                        <Link to={`/catalogue/${post.opportunity.id}`} className="award-tag-ribbon">
                          <span>🏛️</span>
                          <span>Linked Award:</span>
                          <span className="award-link-name">{post.opportunity.name}</span>
                          <span>➔</span>
                        </Link>
                      </div>
                    ) : null}

                    <div className="post-body-container">
                      <h2 className="post-title-text">{post.title}</h2>
                      <p className="post-body-text">{post.body}</p>
                    </div>

                    <div className="post-actions-bar">
                      <div className="post-micro-actions">
                        <button
                          type="button"
                          className={`feed-action-btn ${post.is_bookmarked ? "active-helpful" : ""}`}
                          onClick={() =>
                            void action(`/community/posts/${post.id}/bookmarks`, post.is_bookmarked ? "DELETE" : "POST")
                          }
                        >
                          <span>{post.is_bookmarked ? "🔖 Saved" : "🔖 Bookmark"}</span>
                        </button>
                        <button
                          type="button"
                          className="feed-action-btn"
                          onClick={() =>
                            setExpandedReplies((prev) => ({ ...prev, [post.id]: !isRepliesOpen }))
                          }
                        >
                          <span>💬 {post.replies?.length ?? post.reply_count} Replies</span>
                        </button>
                      </div>

                      <Link
                        to={`/assistant?prompt=${encodeURIComponent(`Fact check and advice for discussion: "${post.title}"`)}`}
                        className="copilot-pill-btn"
                      >
                        <span>🤖</span> Audit with Copilot
                      </Link>
                    </div>

                    {isRepliesOpen || post.replies?.length ? (
                      <div className="post-replies-thread">
                        {post.replies?.map((item) => (
                          <div className="reply-item-bubble" key={item.id}>
                            <div className="reply-avatar">{authorInitials(item.author.display_name)}</div>
                            <div className="reply-content-box">
                              <div className="reply-author-line">
                                <strong>{item.author.display_name}</strong>
                                <span>{formatRelativeTime(item.created_at)}</span>
                              </div>
                              <p>{item.body}</p>
                            </div>
                          </div>
                        ))}

                        {canParticipate ? (
                          <div className="reply-composer-row">
                            <input
                              value={replyText[post.id] ?? ""}
                              onChange={(event) =>
                                setReplyText({ ...replyText, [post.id]: event.target.value })
                              }
                              placeholder="Write a careful, constructive reply..."
                              minLength={2}
                              maxLength={4000}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                  e.preventDefault();
                                  void reply(post.id);
                                }
                              }}
                            />
                            <button
                              type="button"
                              className="button button-primary reply-send-btn"
                              onClick={() => void reply(post.id)}
                            >
                              Reply
                            </button>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </article>
                );
              })
            )}
          </div>

          {user.role === "admin" ? (
            <section className="clean-feed-card community-moderation-panel">
              <p className="eyebrow">Moderator Workspace</p>
              <h2>Open Reports ({reports.length})</h2>
              {reports.length ? (
                <div className="moderation-reports-list">
                  {reports.map((item) => (
                    <article className="moderation-report-card" key={item.report.id}>
                      <strong>{item.content_type} by {item.author.display_name}</strong>
                      <p className="report-preview">"{item.content_preview}"</p>
                      <p className="report-reason">Reason: {labelTopic(item.report.reason)} {item.report.detail ? `· ${item.report.detail}` : ""}</p>
                      <div className="moderation-actions-row">
                        <button type="button" className="button button-quiet" onClick={() => void moderate("hide", item)}>
                          Hide Content
                        </button>
                        <button type="button" className="button button-quiet" onClick={() => void moderate("resolve_report", item)}>
                          Resolve Report
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No open reports in the moderation queue.</p>
              )}
            </section>
          ) : null}
        </section>

        <aside className="community-sidebar-column">
          <div className="sidebar-card passport-card">
            <div className="passport-header">
              <span className="passport-eyebrow">My Scholar Passport</span>
              <span className="status-pill-green">Active</span>
            </div>

            <div className="passport-user-row">
              <div className="scholar-avatar avatar-uk w-10 h-10">
                {authorInitials(displayName || user.email || "WM")}
              </div>
              <div className="passport-user-info">
                <strong>{displayName || user.email?.split("@")[0] || "Scholar"}</strong>
                <span>Target: Global Awards</span>
              </div>
            </div>

            <p className="passport-disclaimer">
              Your public handle is visible to members. Profile data, applications, and assistant chats remain 100% private.
            </p>
          </div>

          <div className="sidebar-card deadlines-card">
            <div className="sidebar-header-row">
              <span className="sidebar-eyebrow">Approaching Deadlines</span>
              <span className="radar-ticker-pill">
                <span className="radar-dot" /> Radar
              </span>
            </div>

            <div className="deadlines-list">
              <Link to="/catalogue" className="deadline-item deadline-urgent">
                <div>
                  <strong>🇬🇧 Chevening 2026</strong>
                  <span>Applications open worldwide</span>
                </div>
                <span className="deadline-badge-urgent">Open</span>
              </Link>

              <Link to="/catalogue" className="deadline-item">
                <div>
                  <strong>🇺🇸 Fulbright US Fellowships</strong>
                  <span>Country commission windows</span>
                </div>
                <span className="deadline-badge-neutral">Open</span>
              </Link>
            </div>
          </div>

          <div className="sidebar-card mentors-card">
            <div className="sidebar-header-row">
              <span className="sidebar-eyebrow">Featured Mentors</span>
              <span className="online-pill">Online</span>
            </div>

            <div className="mentors-list">
              <div className="mentor-row">
                <div className="mentor-left">
                  <div className="scholar-avatar avatar-uk w-8 h-8 text-[10px]">FA</div>
                  <div>
                    <strong>Farhan A.</strong>
                    <span>Oxford '24 · Chevening</span>
                  </div>
                </div>
                <Link to="/assistant?prompt=Ask%20about%20Chevening%20leadership%20essay" className="mentor-ask-btn">
                  Ask
                </Link>
              </div>

              <div className="mentor-row">
                <div className="mentor-left">
                  <div className="scholar-avatar avatar-us w-8 h-8 text-[10px]">KL</div>
                  <div>
                    <strong>Kavitha L.</strong>
                    <span>Columbia '25 · Fulbright</span>
                  </div>
                </div>
                <Link to="/assistant?prompt=Ask%20about%20Fulbright%20interview" className="mentor-ask-btn">
                  Ask
                </Link>
              </div>
            </div>
          </div>

          <div className="sidebar-card prompt-vault-card">
            <div className="vault-header">
              <span>🤖</span>
              <span className="sidebar-eyebrow text-teal">Copilot Prompt Vault</span>
            </div>

            <div className="vault-chips-stack">
              <Link to="/assistant?prompt=Review%20my%20leadership%20essay%20using%20STAR%20framework" className="ai-prompt-chip">
                <span>✨ STAR Leadership Review</span>
                <span>➔</span>
              </Link>
              <Link to="/assistant?prompt=Simulate%20scholarship%20interview%20panel" className="ai-prompt-chip">
                <span>🎙️ Mock Panel Interview</span>
                <span>➔</span>
              </Link>
              <Link to="/assistant?prompt=Check%20scholarship%20document%20checklist" className="ai-prompt-chip">
                <span>📁 Document Integrity Audit</span>
                <span>➔</span>
              </Link>
            </div>
          </div>

          <div className="sidebar-trust-footnote">
            <p>🛡️ Zero PII Policy · Official Statutory RAG Grounding</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
