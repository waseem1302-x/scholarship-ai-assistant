import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { formatDate } from "../catalogue/catalogue";
import { applyReviewAction, getAdminWorkspace, importOpportunities, reviewActions } from "./admin";
import type { DataQualityIssue, ImportResponse, ReviewQueueItem } from "./types";

function requestMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function IssueList({ issues }: { issues: DataQualityIssue[] }) {
  if (!issues.length) return <p className="admin-empty">No data-quality issues need attention.</p>;
  return <ul className="issue-list">{issues.map((issue) => <li key={`${issue.opportunity_id}-${issue.code}`}><span className={`severity severity-${issue.severity}`}>{issue.severity}</span><div><strong>{issue.opportunity_name}</strong><p>{issue.message}</p><small>{issue.code.replaceAll("_", " ")}</small></div></li>)}</ul>;
}

function ReviewCard({ item, onChanged }: { item: ReviewQueueItem; onChanged: () => void }) {
  const [action, setAction] = useState(reviewActions[0].value);
  const [sourceId, setSourceId] = useState(item.opportunity.source.id);
  const [notes, setNotes] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedAction = reviewActions.find((itemAction) => itemAction.value === action)!;

  async function submit() {
    if (selectedAction.needsNotes && !notes.trim()) {
      setError("Add reviewer notes for this action.");
      return;
    }
    if (!window.confirm(`${selectedAction.label} “${item.opportunity.name}”? This records an audit event.`)) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await applyReviewAction(item.opportunity.id, action, sourceId, notes, password);
      setPassword("");
      onChanged();
    } catch (requestError) {
      setError(requestMessage(requestError, "Unable to record the review action."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return <article className="review-card"><div className="review-card-header"><div><p className="eyebrow">{item.opportunity.status} · {item.opportunity.verification_status.replaceAll("_", " ")}</p><h2>{item.opportunity.name}</h2><p>{item.opportunity.provider_name} · {item.opportunity.country} · {item.opportunity.degree_level.replaceAll("_", " ")}</p></div><a className="detail-link" href={item.opportunity.source.url} target="_blank" rel="noreferrer">Open source</a></div>
    <IssueList issues={item.reasons} />
    <div className="review-evidence"><strong>{item.opportunity.source.title}</strong><p>{item.opportunity.source.relevant_excerpt}</p><small>Last verified {formatDate(item.opportunity.source.last_verified_at)}</small></div>
    <div className="review-controls"><label>Review action<select value={action} onChange={(event) => setAction(event.target.value as typeof action)}>{reviewActions.map((itemAction) => <option key={itemAction.value} value={itemAction.value}>{itemAction.label}</option>)}</select></label><label>Source<select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>{item.opportunity.sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label><label className="wide">Reviewer notes{selectedAction.needsNotes ? " (required)" : " (optional)"}<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Describe the evidence or decision." /></label><label className="wide">Administrator password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Required to confirm this action" /></label></div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}<div className="card-actions"><button className="button button-primary" type="button" onClick={submit} disabled={isSubmitting}>{isSubmitting ? "Recording..." : selectedAction.label}</button></div>
  </article>;
}

function ImportPanel({ onChanged }: { onChanged: () => void }) {
  const [format, setFormat] = useState<"json" | "csv">("json");
  const [content, setContent] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<ImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  async function submit() {
    setError(null); setResult(null); setIsSubmitting(true);
    try {
      const response = await importOpportunities(format, content, dryRun, password);
      setResult(response); setPassword("");
      if (!dryRun && response.imported_count) onChanged();
    } catch (requestError) { setError(requestMessage(requestError, "Unable to import these opportunities.")); } finally { setIsSubmitting(false); }
  }
  return <section className="admin-panel import-panel"><div><p className="eyebrow">Controlled import</p><h2>Bring new records into review safely.</h2><p>Imports always enter as drafts with sources needing review. Start with a dry run to inspect every row.</p></div><div className="import-fields"><label>Format<select value={format} onChange={(event) => setFormat(event.target.value as typeof format)}><option value="json">JSON rows</option><option value="csv">CSV text</option></select></label><label className="toggle-label"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Dry run only</label><label className="wide">{format === "json" ? "Opportunity rows (JSON)" : "CSV content"}<textarea rows={10} value={content} onChange={(event) => setContent(event.target.value)} placeholder={format === "json" ? '[{ "name": "...", "source": { "url": "..." } }]' : "name,provider_name,country,..."} /></label><label className="wide">Administrator password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Required to confirm this import" /></label></div>{error ? <p className="form-error" role="alert">{error}</p> : null}<button className="button button-primary" type="button" onClick={submit} disabled={isSubmitting}>{isSubmitting ? "Importing..." : dryRun ? "Run dry import" : "Import records"}</button>{result ? <div className="import-result" role="status"><strong>{result.dry_run ? "Dry run complete" : "Import complete"}</strong><p>{result.imported_count} imported · {result.duplicate_count} duplicates · {result.failed_count} failed out of {result.total_rows} rows.</p>{result.results.some((row) => row.errors.length || row.warnings.length) ? <ul>{result.results.filter((row) => row.errors.length || row.warnings.length).map((row) => <li key={row.row_number}>Row {row.row_number}: {[...row.errors, ...row.warnings].join(" ")}</li>)}</ul> : null}</div> : null}</section>;
}

export function AdminPage() {
  const { user, isRestoring } = useAuth();
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [issues, setIssues] = useState<DataQualityIssue[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setIsLoading(true); setError(null); void getAdminWorkspace().then(([queueResponse, issueResponse]) => { setQueue(queueResponse.items); setIssues(issueResponse.items); }).catch((requestError: unknown) => setError(requestMessage(requestError, "Unable to load the administrator workspace."))).finally(() => setIsLoading(false)); };
  useEffect(() => { if (user?.role === "admin") load(); }, [user]);
  if (isRestoring) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "admin") return <Navigate replace to="/dashboard" />;
  return <main className="admin-page page-width" aria-busy={isLoading}><section className="tool-header"><div><p className="eyebrow">Administrator workspace</p><h1>Keep the catalogue trustworthy.</h1><p className="lead">Review evidence, resolve quality signals, and import records without letting unverified data reach students.</p></div><Link className="button button-quiet" to="/catalogue">View public catalogue</Link></section>{isLoading ? <div className="catalogue-message">Loading review work...</div> : null}{error ? <div className="catalogue-message error-message" role="alert"><h2>We could not load the workspace.</h2><p>{error}</p><button className="button button-quiet" type="button" onClick={load}>Try again</button></div> : null}{!isLoading && !error ? <><section className="admin-summary"><div><strong>{queue.length}</strong><span>review items</span></div><div><strong>{issues.filter((issue) => issue.severity === "high").length}</strong><span>high-severity signals</span></div><div><strong>{issues.length}</strong><span>quality signals shown</span></div></section><div className="admin-layout"><section className="admin-panel"><p className="eyebrow">Data quality dashboard</p><h2>Signals worth inspecting</h2><IssueList issues={issues} /></section><ImportPanel onChanged={load} /></div><section className="review-section"><div className="result-heading"><div><p className="eyebrow">Review queue</p><h2>Decisions that affect public visibility</h2></div><p className="result-count">Showing up to 50 items</p></div>{queue.length ? <div className="review-list">{queue.map((item) => <ReviewCard key={item.opportunity.id} item={item} onChanged={load} />)}</div> : <div className="catalogue-message"><h2>Review queue is clear.</h2><p>There are no medium- or high-severity records waiting for a reviewer decision.</p></div>}</section></> : null}</main>;
}
