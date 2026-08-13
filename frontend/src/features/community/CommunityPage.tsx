import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { ApiError, apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";

type Author = { id: string; display_name: string };
type Reply = { id: string; body: string; author: Author; is_owner: boolean; created_at: string };
type Post = {
  id: string; title: string; body: string; topic: string; author: Author; is_owner: boolean;
  is_bookmarked: boolean; reply_count: number; created_at: string;
  opportunity: { id: string; name: string } | null; replies?: Reply[];
};
type Feed = { posts: Post[]; total: number; has_next: boolean };
type Preferences = { display_name: string | null; consented: boolean; suspended: boolean; notice_version: string };
type Report = { id: string; content_type: "post" | "reply"; content_id: string; content_preview: string; author: Author; status: string; report: { id: string; reason: string; detail: string | null } };
type ReportQueue = { reports: Report[] };

const topics = ["question", "application_process", "documents", "interview", "timeline", "official_source_update", "general"];
const label = (value: string) => value.replaceAll("_", " ");
const failure = (error: unknown) => error instanceof ApiError ? error.message : "We could not complete that community action.";

export function CommunityPage() {
  const { user, isRestoring } = useAuth();
  const [searchParams] = useSearchParams();
  const opportunityId = searchParams.get("opportunity") ?? undefined;
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [title, setTitle] = useState(""); const [body, setBody] = useState(""); const [topic, setTopic] = useState("question");
  const [displayName, setDisplayName] = useState(""); const [replyText, setReplyText] = useState<Record<string, string>>({});
  const [query, setQuery] = useState(""); const [notice, setNotice] = useState<string | null>(null); const [error, setError] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const canParticipate = Boolean(preferences?.consented && !preferences.suspended);

  async function load() {
    try {
      const [nextPreferences, nextFeed] = await Promise.all([
        apiClient.request<Preferences>("/community/preferences"),
        apiClient.request<Feed>(`/community/posts${query ? `?q=${encodeURIComponent(query)}` : ""}`),
      ]);
      setPreferences(nextPreferences); setDisplayName(nextPreferences.display_name ?? ""); setFeed(nextFeed);
      if (user?.role === "admin") setReports((await apiClient.request<ReportQueue>("/community/admin/reports")).reports);
    } catch (requestError) { setError(failure(requestError)); }
  }
  useEffect(() => { if (user) void load(); }, [user]);
  if (!isRestoring && !user) return <Navigate replace to="/auth" />;
  if (!user) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session…</main>;

  async function participate(event: FormEvent) {
    event.preventDefault(); setError(null);
    try { await apiClient.request("/community/preferences", { method: "PUT", body: JSON.stringify({ display_name: displayName, consent: true }) }); setNotice("You can now participate using your community display name."); await load(); }
    catch (requestError) { setError(failure(requestError)); }
  }
  async function publish(event: FormEvent) {
    event.preventDefault(); setError(null);
    try { await apiClient.request("/community/posts", { method: "POST", body: JSON.stringify({ title, body, topic, opportunity_id: opportunityId }) }); setTitle(""); setBody(""); setNotice("Your post is now visible to the community."); await load(); }
    catch (requestError) { setError(failure(requestError)); }
  }
  async function reply(postId: string) {
    const next = replyText[postId]?.trim(); if (!next) return;
    try { await apiClient.request(`/community/posts/${postId}/replies`, { method: "POST", body: JSON.stringify({ body: next }) }); setReplyText({ ...replyText, [postId]: "" }); await load(); }
    catch (requestError) { setError(failure(requestError)); }
  }
  async function action(path: string, method: "POST" | "DELETE", body?: object) {
    try { await apiClient.request(path, { method, body: body ? JSON.stringify(body) : undefined }); await load(); }
    catch (requestError) { setError(failure(requestError)); }
  }
  async function moderate(action: string, item: Report) {
    try { await apiClient.request("/community/admin/moderation-actions", { method: "POST", body: JSON.stringify(action === "resolve_report" ? { action, report_id: item.report.id } : { action, [`${item.content_type}_id`]: item.content_id, reason: "Moderator action" }) }); await load(); }
    catch (requestError) { setError(failure(requestError)); }
  }

  return <main className="community-page page-width">
    <section className="tool-header"><div><p className="eyebrow">Scholarship-only community</p><h1>Learn from applicants. Confirm with official sources.</h1><p>Member experiences are not official scholarship advice. Never share documents, contact details, credentials, or private application information.</p></div><Link className="button button-quiet" to="/catalogue">Browse verified catalogue</Link></section>
    {error ? <p className="form-error" role="alert">{error}</p> : null}{notice ? <p className="form-success" role="status">{notice}</p> : null}
    {!preferences?.consented ? <form className="community-notice" onSubmit={participate}><h2>Choose how you appear</h2><p>Your display name is public to members. Your email, profile, applications, assistant history, and Document Lab remain private.</p><label>Community display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} minLength={3} maxLength={40} required /></label><label className="toggle-label"><input type="checkbox" required /> I agree to keep discussion scholarship-related and to report unsafe content.</label><button className="button button-primary">Join community</button></form> : preferences.suspended ? <section className="catalogue-message error-message"><h2>Participation is suspended</h2><p>You can still read visible discussions, but cannot post or interact. Contact support if you need clarification.</p></section> : <form className="community-composer" onSubmit={publish}><h2>Start a scholarship discussion</h2>{opportunityId ? <p className="form-success">This post will be linked to the verified scholarship you came from.</p> : null}<label>Topic<select value={topic} onChange={(event) => setTopic(event.target.value)}>{topics.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></label><label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} minLength={4} maxLength={160} required /></label><label>What would help other applicants?<textarea value={body} onChange={(event) => setBody(event.target.value)} minLength={10} maxLength={6000} required /></label><button className="button button-primary">Publish post</button></form>}
    <section className="community-feed"><div className="result-heading"><div><p className="eyebrow">Member discussions</p><h2>Scholarship preparation, in context</h2></div><form onSubmit={(event) => { event.preventDefault(); void load(); }}><label className="sr-only" htmlFor="community-search">Search discussions</label><input id="community-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search discussions" /><button className="button button-quiet">Search</button></form></div>
      {!feed?.posts.length ? <div className="catalogue-message"><h2>No discussions yet</h2><p>Be the first to ask a scholarship-related question or share a careful application tip.</p></div> : feed.posts.map((post) => <article className="community-post" key={post.id}><div className="community-post-meta"><span>{label(post.topic)}</span><span>by {post.author.display_name}</span></div><h3>{post.title}</h3><p>{post.body}</p>{post.opportunity ? <Link to={`/catalogue/${post.opportunity.id}`}>Verified scholarship: {post.opportunity.name}</Link> : null}{post.replies?.length ? <section className="community-replies" aria-label={`Replies to ${post.title}`}>{post.replies.map((item) => <article key={item.id}><strong>{item.author.display_name}</strong><p>{item.body}</p></article>)}</section> : null}{canParticipate ? <><div className="card-actions"><button className="button button-quiet" onClick={() => void action(`/community/posts/${post.id}/bookmarks`, post.is_bookmarked ? "DELETE" : "POST")}>{post.is_bookmarked ? "Remove bookmark" : "Bookmark"}</button>{!post.is_owner ? <><button className="button button-quiet" onClick={() => void action("/community/blocks", "POST", { user_id: post.author.id })}>Block author</button><button className="button button-quiet" onClick={() => void action("/community/reports", "POST", { post_id: post.id, reason: "misleading", detail: "Please review this community content." })}>Report</button></> : <button className="button button-quiet" onClick={() => void action(`/community/posts/${post.id}`, "DELETE")}>Delete post</button>}</div><label>Reply<textarea value={replyText[post.id] ?? ""} onChange={(event) => setReplyText({ ...replyText, [post.id]: event.target.value })} minLength={2} maxLength={4000} /></label><button className="button button-primary" onClick={() => void reply(post.id)}>Add reply</button></> : null}</article>)}</section>
    {user.role === "admin" ? <section className="community-moderation"><p className="eyebrow">Moderator workspace</p><h2>Open reports</h2>{reports.length ? reports.map((item) => <article key={item.report.id}><strong>{item.content_type} by {item.author.display_name}</strong><p>{item.content_preview}</p><p>Reported for {label(item.report.reason)}{item.report.detail ? `: ${item.report.detail}` : ""}</p><button className="button button-quiet" onClick={() => void moderate("hide", item)}>Hide content</button><button className="button button-quiet" onClick={() => void moderate("resolve_report", item)}>Resolve report</button></article>) : <p>No open reports.</p>}</section> : null}
  </main>;
}
