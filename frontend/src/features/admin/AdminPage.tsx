import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { formatDate } from "../catalogue/catalogue";
import {
  applyReviewAction,
  getAdminOpportunities,
  getAdminWorkspace,
  importFormatForFile,
  importOpportunities,
  importTemplates,
  recordSourceCheck,
  reverifySource,
  reviewActions,
  type ImportFormat,
} from "./admin";
import {
  defaultAdminOpportunityFilters,
  type AdminOpportunity,
  type AdminOpportunityFilters,
  type AdminOpportunitySearchResponse,
  type DataQualityIssue,
  type DataQualityResponse,
  type ImportResponse,
  type ReviewQueueItem,
  type ReviewQueueResponse,
} from "./types";

function requestMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function IssueList({ issues }: { issues: DataQualityIssue[] }) {
  if (!issues.length) return <p className="admin-empty">No data-quality issues need attention.</p>;
  return <ul className="issue-list">{issues.map((issue) => <li key={`${issue.opportunity_id}-${issue.code}`}><span className={`severity severity-${issue.severity}`}>{issue.severity}</span><div><strong>{issue.opportunity_name}</strong><p>{issue.message}</p><small>{issue.code.replaceAll("_", " ")}</small></div></li>)}</ul>;
}

function PageControls({ label, offset, total, limit, hasNext, onChange }: { label: string; offset: number; total: number; limit: number; hasNext: boolean; onChange: (offset: number) => void }) {
  if (!total) return null;
  return <nav className="pagination" aria-label={`${label} pagination`}><button className="button button-quiet" type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button><span>Page {Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(total / limit))}</span><button className="button button-quiet" type="button" disabled={!hasNext} onClick={() => onChange(offset + limit)}>Next</button></nav>;
}

function ReviewCard({ item, onChanged }: { item: ReviewQueueItem; onChanged: () => void }) {
  const [action, setAction] = useState(reviewActions[0].value);
  const [sourceId, setSourceId] = useState(item.opportunity.source.id);
  const [notes, setNotes] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceCheckHash, setSourceCheckHash] = useState("");
  const [sourceCheckSummary, setSourceCheckSummary] = useState("");
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  const selectedAction = reviewActions.find((itemAction) => itemAction.value === action)!;

  async function run(operation: () => Promise<void>, fallback: string, success: string) {
    setIsSubmitting(true); setError(null); setOperationMessage(null);
    try { await operation(); setPassword(""); setOperationMessage(success); onChanged(); }
    catch (requestError) { setError(requestMessage(requestError, fallback)); }
    finally { setIsSubmitting(false); }
  }

  function submitReview() {
    if (selectedAction.needsNotes && !notes.trim()) { setError("Add reviewer notes for this action."); return; }
    if (!window.confirm(`${selectedAction.label} “${item.opportunity.name}”? This records an audit event.`)) return;
    void run(() => applyReviewAction(item.opportunity.id, action, sourceId, notes, password), "Unable to record the review action.", "Review action recorded.");
  }

  function submitSourceCheck() {
    const normalizedHash = sourceCheckHash.trim();
    if (normalizedHash && !/^[a-fA-F0-9]{32,64}$/.test(normalizedHash)) { setError("A source content hash must contain 32 to 64 hexadecimal characters."); return; }
    if (!window.confirm(`Record a source check for “${item.opportunity.name}”? This creates an audit event.`)) return;
    void run(async () => { await recordSourceCheck(sourceId, normalizedHash, sourceCheckSummary, password); setSourceCheckHash(""); setSourceCheckSummary(""); }, "Unable to record the source check.", "Source check recorded. Its verification state changes only when a changed hash is supplied.");
  }

  function submitReverification() {
    if (!window.confirm(`Mark the selected official source for “${item.opportunity.name}” as reverified? This can restore public visibility.`)) return;
    void run(() => reverifySource(item.opportunity.id, sourceId, notes, password), "Unable to reverify the source.", "Source reverified and the scholarship record was updated.");
  }

  return <article className="review-card"><div className="review-card-header"><div><p className="eyebrow">{item.opportunity.status} · {item.opportunity.verification_status.replaceAll("_", " ")}</p><h2>{item.opportunity.name}</h2><p>{item.opportunity.provider_name} · {item.opportunity.country} · {item.opportunity.degree_level.replaceAll("_", " ")}</p></div><a className="detail-link" href={item.opportunity.source.url} target="_blank" rel="noreferrer">Open source</a></div><IssueList issues={item.reasons} /><div className="review-evidence"><strong>{item.opportunity.source.title}</strong><p>{item.opportunity.source.relevant_excerpt}</p><small>Last verified {formatDate(item.opportunity.source.last_verified_at)}</small></div><div className="review-controls"><label>Review action<select value={action} onChange={(event) => setAction(event.target.value as typeof action)}>{reviewActions.map((itemAction) => <option key={itemAction.value} value={itemAction.value}>{itemAction.label}</option>)}</select></label><label>Source<select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>{item.opportunity.sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label><label className="wide">Reviewer notes{selectedAction.needsNotes ? " (required)" : " (optional)"}<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Describe the evidence or decision." /></label><label className="wide">Administrator password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Required to confirm this action" /></label></div><section className="source-check-controls"><p className="eyebrow">Source checks and re-verification</p><p>Record the evidence check first. A changed content hash automatically returns the source to review; re-verify only after confirming the official source.</p><label>Observed content hash (optional)<input value={sourceCheckHash} onChange={(event) => setSourceCheckHash(event.target.value)} placeholder="SHA-256 or comparable hash" /></label><label>Check summary (optional)<textarea rows={2} value={sourceCheckSummary} onChange={(event) => setSourceCheckSummary(event.target.value)} placeholder="What you checked and what changed." /></label></section>{error ? <p className="form-error" role="alert">{error}</p> : null}{operationMessage ? <p className="form-success" role="status">{operationMessage}</p> : null}<div className="card-actions"><button className="button button-primary" type="button" onClick={submitReview} disabled={isSubmitting}>{isSubmitting ? "Recording..." : selectedAction.label}</button><button className="button button-quiet" type="button" onClick={submitSourceCheck} disabled={isSubmitting}>{isSubmitting ? "Recording..." : "Record source check"}</button><button className="button button-quiet" type="button" onClick={submitReverification} disabled={isSubmitting}>{isSubmitting ? "Reverifying..." : "Reverify selected source"}</button></div></article>;
}

function AdminRecordList({ records }: { records: AdminOpportunity[] }) {
  if (!records.length) return <p className="admin-empty">No scholarship records match these filters.</p>;
  return <ul className="issue-list admin-record-list">{records.map((record) => <li key={record.id}><span className={`severity severity-${record.status === "active" ? "low" : "medium"}`}>{record.status}</span><div><strong>{record.name}</strong><p>{record.provider_name} · {record.country} · {record.degree_level.replaceAll("_", " ")}</p><small>{record.verification_status.replaceAll("_", " ")} · deadline {formatDate(record.application_deadline)}</small></div></li>)}</ul>;
}

function AdminCataloguePanel() {
  const [draft, setDraft] = useState<AdminOpportunityFilters>(defaultAdminOpportunityFilters);
  const [applied, setApplied] = useState<AdminOpportunityFilters>(defaultAdminOpportunityFilters);
  const [response, setResponse] = useState<AdminOpportunitySearchResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  function load(nextFilters = applied, nextOffset = offset, signal?: AbortSignal) { setIsLoading(true); setError(null); void getAdminOpportunities(nextFilters, nextOffset, signal).then((next) => { setResponse(next); setApplied(nextFilters); setOffset(nextOffset); }).catch((requestError: unknown) => { if (!(requestError instanceof DOMException && requestError.name === "AbortError")) setError(requestMessage(requestError, "Unable to load scholarship records.")); }).finally(() => { if (!signal?.aborted) setIsLoading(false); }); }
  useEffect(() => { const controller = new AbortController(); load(defaultAdminOpportunityFilters, 0, controller.signal); return () => controller.abort(); }, []);
  function update(key: keyof AdminOpportunityFilters, value: string) { setDraft((current) => ({ ...current, [key]: value })); }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); load(draft, 0); }
  function clear() { setDraft(defaultAdminOpportunityFilters); load(defaultAdminOpportunityFilters, 0); }
  const pagination = response?.pagination;
  return <section className="admin-panel admin-catalogue-panel"><div><p className="eyebrow">Scholarship records</p><h2>Find records across the review lifecycle.</h2></div><form className="admin-filters" onSubmit={submit} aria-label="Filter scholarship records"><label>Search<input value={draft.search_query} onChange={(event) => update("search_query", event.target.value)} placeholder="Name, field, or notes" /></label><label>Country<input value={draft.country} onChange={(event) => update("country", event.target.value)} placeholder="Malaysia" /></label><label>Status<select value={draft.status} onChange={(event) => update("status", event.target.value)}><option value="">Any status</option><option value="draft">Draft</option><option value="active">Active</option><option value="expired">Expired</option><option value="archived">Archived</option></select></label><label>Verification<select value={draft.verification_status} onChange={(event) => update("verification_status", event.target.value)}><option value="">Any verification state</option><option value="needs_review">Needs review</option><option value="officially_verified">Officially verified</option><option value="conflicting_information">Conflicting information</option><option value="expired">Expired</option></select></label><label className="toggle-label"><input type="checkbox" checked={draft.needs_review === "true"} onChange={(event) => update("needs_review", event.target.checked ? "true" : "")} /> Needs review</label><div className="filter-actions"><button className="button button-primary" type="submit">Apply filters</button><button className="button button-quiet" type="button" onClick={clear}>Clear</button></div></form>{error ? <p className="form-error" role="alert">{error}</p> : null}{isLoading ? <p className="admin-empty">Loading scholarship records...</p> : <><p className="result-count">Showing {pagination?.count ?? 0} of {pagination?.total ?? 0}</p><AdminRecordList records={response?.items ?? []} /><PageControls label="Scholarship records" offset={offset} total={pagination?.total ?? 0} limit={pagination?.limit ?? 20} hasNext={pagination?.has_next ?? false} onChange={(nextOffset) => load(applied, nextOffset)} /></>}</section>;
}

function ImportPanel({ onChanged }: { onChanged: () => void }) {
  const [format, setFormat] = useState<ImportFormat>("json");
  const [content, setContent] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<ImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileMessage, setFileMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  function downloadTemplate(nextFormat: ImportFormat) { const blob = new Blob([importTemplates[nextFormat]], { type: nextFormat === "json" ? "application/json" : "text/csv" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `opportunity-import-template.${nextFormat}`; document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url); }
  async function loadFile(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (!file) return; const nextFormat = importFormatForFile(file.name); if (!nextFormat) { setError("Choose a .json or .csv opportunity import file."); return; } if (nextFormat === "csv" && file.size > 200_000) { setError("CSV import files are limited to 200 KB by the server."); return; } try { const nextContent = await file.text(); setFormat(nextFormat); setContent(nextContent); setResult(null); setError(null); setFileMessage(`Loaded ${file.name}. Review the contents before running a dry import.`); } catch { setError("The selected file could not be read."); } }
  async function submit() { setError(null); setResult(null); setIsSubmitting(true); try { const response = await importOpportunities(format, content, dryRun, password); setResult(response); setPassword(""); if (!dryRun && response.imported_count) onChanged(); } catch (requestError) { setError(requestMessage(requestError, "Unable to import these opportunities.")); } finally { setIsSubmitting(false); } }
  return <section className="admin-panel import-panel"><div><p className="eyebrow">Controlled import</p><h2>Bring new records into review safely.</h2><p>Imports always enter as drafts with sources needing review. Start with a dry run to inspect every row.</p></div><div className="import-tools"><label className="button button-quiet file-upload-control">Choose CSV or JSON file<input aria-label="Upload opportunity import file" type="file" accept=".csv,.json,text/csv,application/json" onChange={loadFile} /></label><button className="button button-quiet" type="button" onClick={() => downloadTemplate(format)}>Download {format.toUpperCase()} template</button></div><p className="import-help">Templates include supported structure and example values. Replace every example with official evidence; selecting a file only loads it for review and does not upload it yet.</p><div className="import-fields"><label>Format<select value={format} onChange={(event) => setFormat(event.target.value as ImportFormat)}><option value="json">JSON rows</option><option value="csv">CSV text</option></select></label><label className="toggle-label"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Dry run only</label><label className="wide">{format === "json" ? "Opportunity rows (JSON)" : "CSV content"}<textarea rows={10} value={content} onChange={(event) => setContent(event.target.value)} placeholder={format === "json" ? '[{ "name": "...", "source": { "url": "..." } }]' : "name,provider_name,country,..."} /></label><label className="wide">Administrator password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Required to confirm this import" /></label></div>{fileMessage ? <p className="form-success" role="status">{fileMessage}</p> : null}{error ? <p className="form-error" role="alert">{error}</p> : null}<button className="button button-primary" type="button" onClick={submit} disabled={isSubmitting}>{isSubmitting ? "Importing..." : dryRun ? "Run dry import" : "Import records"}</button>{result ? <div className="import-result" role="status"><strong>{result.dry_run ? "Dry run complete" : "Import complete"}</strong><p>{result.imported_count} imported · {result.duplicate_count} duplicates · {result.failed_count} failed out of {result.total_rows} rows.</p>{result.results.some((row) => row.errors.length || row.warnings.length) ? <ul>{result.results.filter((row) => row.errors.length || row.warnings.length).map((row) => <li key={row.row_number}>Row {row.row_number}: {[...row.errors, ...row.warnings].join(" ")}</li>)}</ul> : null}</div> : null}</section>;
}

export function AdminPage() {
  const { user, isRestoring } = useAuth();
  const [queueResponse, setQueueResponse] = useState<ReviewQueueResponse | null>(null);
  const [issueResponse, setIssueResponse] = useState<DataQualityResponse | null>(null);
  const [queueOffset, setQueueOffset] = useState(0);
  const [issueOffset, setIssueOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  function load(nextQueueOffset = queueOffset, nextIssueOffset = issueOffset, signal?: AbortSignal) { setIsLoading(true); setError(null); void getAdminWorkspace({ queueOffset: nextQueueOffset, issueOffset: nextIssueOffset }, signal).then(([nextQueue, nextIssues]) => { setQueueResponse(nextQueue); setIssueResponse(nextIssues); setQueueOffset(nextQueueOffset); setIssueOffset(nextIssueOffset); }).catch((requestError: unknown) => { if (!(requestError instanceof DOMException && requestError.name === "AbortError")) setError(requestMessage(requestError, "Unable to load the administrator workspace.")); }).finally(() => { if (!signal?.aborted) setIsLoading(false); }); }
  useEffect(() => { const controller = new AbortController(); if (user?.role === "admin") load(0, 0, controller.signal); return () => controller.abort(); }, [user]);
  if (isRestoring) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "admin") return <Navigate replace to="/dashboard" />;
  const queue = queueResponse?.items ?? []; const issues = issueResponse?.items ?? [];
  return <main className="admin-page page-width" aria-busy={isLoading}><section className="tool-header"><div><p className="eyebrow">Administrator workspace</p><h1>Keep scholarships trustworthy.</h1><p className="lead">Review evidence, resolve quality signals, and import records without letting unverified data reach students.</p></div><Link className="button button-quiet" to="/catalogue">View public scholarships</Link></section>{isLoading ? <div className="catalogue-message">Loading review work...</div> : null}{error ? <div className="catalogue-message error-message" role="alert"><h2>We could not load the workspace.</h2><p>{error}</p><button className="button button-quiet" type="button" onClick={() => load()}>Try again</button></div> : null}{!isLoading && !error ? <><section className="admin-summary"><div><strong>{queueResponse?.pagination.total ?? 0}</strong><span>review items</span></div><div><strong>{issues.filter((issue) => issue.severity === "high").length}</strong><span>high-severity signals on this page</span></div><div><strong>{issueResponse?.pagination.total ?? 0}</strong><span>quality signals</span></div></section><div className="admin-layout"><section className="admin-panel"><p className="eyebrow">Data quality dashboard</p><h2>Signals worth inspecting</h2><IssueList issues={issues} /><PageControls label="Data-quality issues" offset={issueOffset} total={issueResponse?.pagination.total ?? 0} limit={issueResponse?.pagination.limit ?? 20} hasNext={issueResponse?.pagination.has_next ?? false} onChange={(nextOffset) => load(queueOffset, nextOffset)} /></section><ImportPanel onChanged={() => load(0, 0)} /></div><AdminCataloguePanel /><section className="review-section"><div className="result-heading"><div><p className="eyebrow">Review queue</p><h2>Decisions that affect public visibility</h2></div><p className="result-count">Showing {queueResponse?.pagination.count ?? 0} of {queueResponse?.pagination.total ?? 0}</p></div>{queue.length ? <div className="review-list">{queue.map((item) => <ReviewCard key={item.opportunity.id} item={item} onChanged={() => load(queueOffset, issueOffset)} />)}</div> : <div className="catalogue-message"><h2>Review queue is clear.</h2><p>There are no medium- or high-severity records waiting for a reviewer decision.</p></div>}<PageControls label="Review queue" offset={queueOffset} total={queueResponse?.pagination.total ?? 0} limit={queueResponse?.pagination.limit ?? 20} hasNext={queueResponse?.pagination.has_next ?? false} onChange={(nextOffset) => load(nextOffset, issueOffset)} /></section></> : null}</main>;
}
