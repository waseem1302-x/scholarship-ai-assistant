import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { deadlineLabel, readableValue } from "../catalogue/catalogue";
import { DirectUrlIngestionPanel } from "./DirectUrlIngestionPanel";
import {
  getAdminCatalogueRecords,
  getAdminWorkspace,
  getAcquiredCandidates,
  getDuplicateSuggestions,
  importFormatForFile,
  importOpportunities,
  importTemplates,
  reviewDuplicateSuggestion,
  type ImportFormat,
} from "./admin";
import type {
  AdminOpportunity,
  DataQualityIssue,
  DataQualityResponse,
  DuplicateSuggestionResponse,
  ImportResponse,
  IngestionCandidate,
  IngestionCandidateResponse,
  ReviewQueueItem,
  ReviewQueueResponse,
} from "./types";

export type ReviewAttentionFilter = "all" | "complete" | "missing_funding" | "missing_deadline" | "missing_eligibility" | "conflicts" | "duplicates" | "stale_sources" | "failed_acquisition";

interface ScholarshipFamilyCard {
  key: string;
  name: string;
  provider: string;
  country: string;
  variants: AdminOpportunity[];
}

function requestMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function sanitizeScholarshipSearch(value: string): string {
  const normalized = value.trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized) ? "" : value;
}

function familyName(value: string): string {
  return value
    .replace(/\s+20\d{2}(?:\s*\/\s*(?:20)?\d{2})?\s*$/i, "")
    .replace(/\s*[—–-]\s*(?:bachelor(?:'s)?|undergraduate|master(?:'s)?|ph\.?d\.?|doctoral|postdoc(?:toral)?)\s*$/i, "")
    .replace(/\s+(?:graduate|undergraduate)\s+degrees?\s*$/i, "")
    .replace(/\s+20\d{2}(?:\s*\/\s*(?:20)?\d{2})?\s*$/i, "")
    .replace(/programme/gi, "Program")
    .trim();
}

function familyKey(record: AdminOpportunity): string {
  return record.catalogue_family_key ?? `${record.provider_name}|${familyName(record.name)}`.toLocaleLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function groupScholarships(records: AdminOpportunity[]): ScholarshipFamilyCard[] {
  const groups = new Map<string, ScholarshipFamilyCard>();
  for (const record of records) {
    const key = familyKey(record);
    const existing = groups.get(key);
    if (existing) {
      existing.variants.push(record);
      if (familyName(record.name).length < existing.name.length) existing.name = familyName(record.name);
      continue;
    }
    groups.set(key, { key, name: familyName(record.name), provider: record.provider_name, country: record.country, variants: [record] });
  }
  return [...groups.values()].sort((left, right) => left.name.localeCompare(right.name));
}

function degreeLabels(family: ScholarshipFamilyCard): string[] {
  const order = ["bachelors", "masters", "phd", "postdoc", "short_course"];
  const levels = new Set(family.variants.flatMap((variant) => variant.degree_levels?.length ? variant.degree_levels : [variant.degree_level]));
  return [...levels].sort((left, right) => order.indexOf(left) - order.indexOf(right)).map(readableValue);
}

function missingEssentials(record: AdminOpportunity): number {
  return [record.tuition_coverage, record.monthly_stipend_amount, record.nationality_eligibility, record.minimum_academic_requirement, record.application_method].filter((value) => !value).length;
}

function readinessMatches(record: AdminOpportunity, item: ReviewQueueItem | undefined, terms: string[]): boolean {
  const readiness = item?.publication_readiness ?? record.publication_readiness;
  return Boolean(readiness?.blocking_reasons.some((reason) => terms.some((term) => `${reason.field_path} ${reason.reason_code}`.includes(term))));
}

export function opportunityMatchesReviewFilter(record: AdminOpportunity, filter: ReviewAttentionFilter, item: ReviewQueueItem | undefined, duplicateIds: Set<string>): boolean {
  const readiness = item?.publication_readiness ?? record.publication_readiness;
  if (filter === "all") return true;
  if (filter === "complete") return readiness?.ready === true;
  if (filter === "missing_funding") return readinessMatches(record, item, ["funding", "tuition", "stipend"]);
  if (filter === "missing_deadline") return readinessMatches(record, item, ["deadline"]);
  if (filter === "missing_eligibility") return readinessMatches(record, item, ["eligibility", "nationality", "academic", "language"]);
  if (filter === "conflicts") return readinessMatches(record, item, ["conflict"]) || Boolean(item?.reasons.some((reason) => reason.code.includes("conflict")));
  if (filter === "duplicates") return duplicateIds.has(record.id);
  if (filter === "stale_sources") return !record.source_is_fresh || readinessMatches(record, item, ["source_stale"]);
  return false;
}

function candidateCoverage(candidate: IngestionCandidate, objective: string): string | undefined {
  const coverage = candidate.proposed_payload?.objective_coverage;
  return coverage && typeof coverage === "object" && !Array.isArray(coverage) ? String((coverage as Record<string, unknown>)[objective] ?? "") : undefined;
}

export function candidateMatchesReviewFilter(candidate: IngestionCandidate, filter: ReviewAttentionFilter, now = Date.now()): boolean {
  if (filter === "all") return candidate.sources.some((source) => source.artifacts.length);
  if (filter === "complete") return ["ready_for_review", "submitted_for_review", "approved"].includes(candidate.status) && !candidate.failure_code && !candidate.conflicts.length && !candidate.duplicate_opportunity_ids.length;
  if (filter === "missing_funding") return !["complete", "not_applicable"].includes(candidateCoverage(candidate, "funding") ?? "");
  if (filter === "missing_deadline") return !["complete", "not_applicable"].includes(candidateCoverage(candidate, "application_timeline") ?? "");
  if (filter === "missing_eligibility") return !["complete", "not_applicable"].includes(candidateCoverage(candidate, "eligibility") ?? "");
  if (filter === "conflicts") return candidate.conflicts.length > 0 || candidate.status === "conflict_detected";
  if (filter === "duplicates") return candidate.duplicate_opportunity_ids.length > 0 || candidate.status === "duplicate_candidate";
  if (filter === "stale_sources") return candidate.sources.some((source) => source.fetched_at && new Date(source.fetched_at).getTime() < now - 90 * 24 * 60 * 60 * 1000);
  return Boolean(candidate.failure_code) || candidate.sources.some((source) => source.failure_code || source.status === "failed");
}

function ScholarshipAdminCard({ family }: { family: ScholarshipFamilyCard }) {
  const anchor = family.variants.find((variant) => variant.degree_level === "masters") ?? family.variants[0];
  const missing = Math.max(...family.variants.map(missingEssentials));
  const verified = family.variants.every((variant) => variant.verification_status === "officially_verified");
  const deadline = family.variants.map((variant) => variant.application_deadline).find(Boolean) ?? null;
  return (
    <article className="opportunity-card admin-scholarship-card">
      <div className="card-topline"><span className={verified ? "verified-badge" : "review-needed-badge"}>{verified ? "Official sources" : "Needs evidence review"}</span><span className="deadline-label">{deadlineLabel(deadline)}</span></div>
      <h2>{family.name}</h2>
      <p className="provider-name">{family.provider}</p>
      <div className="tag-list"><span>{family.country}</span>{degreeLabels(family).map((level) => <span key={level}>{level}</span>)}</div>
      <p className="funding-summary">{anchor.funding_summary}</p>
      <div className="admin-card-health"><span><strong>{family.variants.length}</strong> study route{family.variants.length === 1 ? "" : "s"}</span><span className={missing ? "has-gaps" : "is-complete"}><strong>{missing}</strong> key gap{missing === 1 ? "" : "s"}</span></div>
      <div className="card-actions"><Link className="button button-primary admin-review-button" to={`/admin/review/${anchor.id}`}>Review scholarship</Link></div>
    </article>
  );
}

function AcquiredCandidateCard({ candidate }: { candidate: IngestionCandidate }) {
  const officialSources = candidate.sources.filter((source) => source.is_official);
  const artifacts = officialSources.reduce((total, source) => total + source.artifacts.length, 0);
  return (
    <article className="review-card acquired-review-card">
      <p className="eyebrow">Acquired · {candidate.status.replaceAll("_", " ")}</p>
      <h3>{candidate.seed_name}</h3>
      <p>{candidate.seed_provider ?? "Provider unknown"} · {candidate.seed_country ?? "Country unknown"}</p>
      <div className="tag-list"><span>{officialSources.length} official source{officialSources.length === 1 ? "" : "s"}</span><span>{artifacts} artifact{artifacts === 1 ? "" : "s"}</span></div>
      <div className="card-actions"><Link className="button button-primary" to={`/admin/acquired/${candidate.id}`}>Inspect acquisition</Link></div>
    </article>
  );
}

function IssueList({ issues }: { issues: DataQualityIssue[] }) {
  if (!issues.length) return <p className="admin-empty">No data-quality issues need attention.</p>;
  return <ul className="issue-list">{issues.map((issue) => <li key={`${issue.opportunity_id}-${issue.code}`}><span className={`severity severity-${issue.severity}`}>{issue.severity}</span><div><strong>{issue.opportunity_name}</strong><p>{issue.message}</p><small>{issue.code.replaceAll("_", " ")}</small></div></li>)}</ul>;
}

function DuplicateResolutionPanel({ suggestions, onChanged }: { suggestions: DuplicateSuggestionResponse; onChanged: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function decide(suggestionId: string, isDuplicate: boolean) {
    setBusyId(suggestionId); setError(null);
    try {
      await reviewDuplicateSuggestion(suggestionId, isDuplicate, password);
      setPassword(""); onChanged();
    } catch (requestError) {
      setError(requestMessage(requestError, "Unable to record the duplicate decision."));
    } finally { setBusyId(null); }
  }

  return <section className="admin-panel duplicate-resolution-panel"><p className="eyebrow">Duplicate resolution</p><h2>Compare possible duplicate records</h2><p>Similarity is a review signal only. Confirm or dismiss each pair explicitly.</p>{suggestions.items.length ? <><label>Administrator password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label><div className="duplicate-pair-list">{suggestions.items.map((suggestion) => <article className="duplicate-pair" key={suggestion.id}><div className="duplicate-record"><strong>{suggestion.opportunity.name}</strong><span>{suggestion.opportunity.provider_name} · {suggestion.opportunity.country} · {readableValue(suggestion.opportunity.degree_level)}</span><small>{suggestion.opportunity.programme_route_id ?? "Route not recorded"} · cycle {suggestion.opportunity.cycle_id ?? "unknown"}</small></div><div className="duplicate-pair-vs">vs</div><div className="duplicate-record"><strong>{suggestion.matched_opportunity.name}</strong><span>{suggestion.matched_opportunity.provider_name} · {suggestion.matched_opportunity.country} · {readableValue(suggestion.matched_opportunity.degree_level)}</span><small>{suggestion.matched_opportunity.programme_route_id ?? "Route not recorded"} · cycle {suggestion.matched_opportunity.cycle_id ?? "unknown"}</small></div><div className="tag-list duplicate-signals">{suggestion.matching_signals.map((signal) => <span key={signal}>{readableValue(signal)}</span>)}</div>{Object.keys(suggestion.conflicting_fields).length ? <dl className="duplicate-conflicts">{Object.entries(suggestion.conflicting_fields).map(([field, values]) => <div key={field}><dt>{readableValue(field)}</dt><dd>{values[0] ?? "not recorded"} / {values[1] ?? "not recorded"}</dd></div>)}</dl> : <p>No structured fields conflict.</p>}<div className="card-actions"><button className="button button-primary" type="button" disabled={busyId === suggestion.id} onClick={() => void decide(suggestion.id, true)}>Confirm duplicate</button><button className="button button-quiet" type="button" disabled={busyId === suggestion.id} onClick={() => void decide(suggestion.id, false)}>Keep separate</button></div></article>)}</div></> : <p className="admin-empty">No duplicate suggestions need review.</p>}{error ? <p className="form-error" role="alert">{error}</p> : null}</section>;
}

function PageControls({ offset, total, limit, hasNext, onChange }: { offset: number; total: number; limit: number; hasNext: boolean; onChange: (offset: number) => void }) {
  if (!total) return null;
  return <nav className="pagination" aria-label="Data quality pagination"><button className="button button-quiet" type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button><span>Page {Math.floor(offset / limit) + 1} of {Math.max(1, Math.ceil(total / limit))}</span><button className="button button-quiet" type="button" disabled={!hasNext} onClick={() => onChange(offset + limit)}>Next</button></nav>;
}

function ImportPanel({ onChanged }: { onChanged: () => void }) {
  const [format, setFormat] = useState<ImportFormat>("json");
  const [content, setContent] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<ImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function downloadTemplate() {
    const blob = new Blob([importTemplates[format]], { type: format === "json" ? "application/json" : "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `opportunity-import-template.${format}`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function loadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    const nextFormat = importFormatForFile(file.name);
    if (!nextFormat) { setError("Choose a .json or .csv file."); return; }
    setFormat(nextFormat);
    setContent(await file.text());
    setMessage(`Loaded ${file.name}. Nothing has been imported yet.`);
    setError(null);
  }

  async function submit() {
    setError(null); setResult(null); setIsSubmitting(true);
    try {
      const next = await importOpportunities(format, content, dryRun, password);
      setResult(next); setPassword("");
      if (!dryRun && next.imported_count) onChanged();
    } catch (requestError) {
      setError(requestMessage(requestError, "Unable to import these records."));
    } finally { setIsSubmitting(false); }
  }

  return (
    <section className="admin-panel import-panel">
      <p className="eyebrow">Controlled import</p><h2>Import records into private review</h2><p>Dry run is on by default. Imported records never publish automatically.</p>
      <div className="import-tools"><label className="button button-quiet file-upload-control">Choose CSV or JSON<input aria-label="Upload opportunity import file" type="file" accept=".csv,.json,text/csv,application/json" onChange={loadFile} /></label><button className="button button-quiet" type="button" onClick={downloadTemplate}>Download template</button></div>
      <div className="import-fields"><label>Format<select value={format} onChange={(event) => setFormat(event.target.value as ImportFormat)}><option value="json">JSON</option><option value="csv">CSV</option></select></label><label className="toggle-label"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Dry run only</label><label className="wide">Records<textarea rows={8} value={content} onChange={(event) => setContent(event.target.value)} /></label><label className="wide">Administrator password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label></div>
      {message ? <p className="form-success">{message}</p> : null}{error ? <p className="form-error" role="alert">{error}</p> : null}
      <button className="button button-primary" type="button" onClick={submit} disabled={isSubmitting}>{isSubmitting ? "Checking..." : dryRun ? "Run dry import" : "Import to review"}</button>
      {result ? <p className="import-result" role="status">{result.imported_count} imported · {result.duplicate_count} duplicates · {result.failed_count} failed.</p> : null}
    </section>
  );
}

export function AdminPage() {
  const { user, isRestoring } = useAuth();
  const [records, setRecords] = useState<AdminOpportunity[]>([]);
  const [queue, setQueue] = useState<ReviewQueueResponse | null>(null);
  const [issues, setIssues] = useState<DataQualityResponse | null>(null);
  const [acquired, setAcquired] = useState<IngestionCandidateResponse | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateSuggestionResponse | null>(null);
  const [issueOffset, setIssueOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [attentionFilter, setAttentionFilter] = useState<ReviewAttentionFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load(nextIssueOffset = issueOffset, signal?: AbortSignal) {
    setIsLoading(true); setError(null);
    void Promise.all([getAdminCatalogueRecords(signal), getAdminWorkspace({ queueOffset: 0, issueOffset: nextIssueOffset }, signal), getAcquiredCandidates(signal), getDuplicateSuggestions(signal)])
      .then(([recordResponse, [queueResponse, issueResponse], acquiredResponse, duplicateResponse]) => {
        setRecords(recordResponse.items); setQueue(queueResponse); setIssues(issueResponse); setAcquired(acquiredResponse); setDuplicates(duplicateResponse); setIssueOffset(nextIssueOffset);
      })
      .catch((requestError: unknown) => { if (!(requestError instanceof DOMException && requestError.name === "AbortError")) setError(requestMessage(requestError, "Unable to load the review catalogue.")); })
      .finally(() => { if (!signal?.aborted) setIsLoading(false); });
  }

  useEffect(() => { const controller = new AbortController(); if (user?.role === "admin") load(0, controller.signal); return () => controller.abort(); }, [user]);

  const families = useMemo(() => groupScholarships(records), [records]);
  const queueById = useMemo(() => new Map((queue?.items ?? []).map((item) => [item.opportunity.id, item])), [queue]);
  const duplicateIds = useMemo(() => new Set((duplicates?.items ?? []).flatMap((suggestion) => [suggestion.opportunity_id, suggestion.matched_opportunity_id])), [duplicates]);
  const filtered = useMemo(() => families.filter((family) => {
    const matchesSearch = !search.trim() || `${family.name} ${family.provider} ${family.country}`.toLowerCase().includes(search.trim().toLowerCase());
    const matchesStatus = status === "all" || family.variants.some((variant) => variant.status === status);
    const matchesAttention = family.variants.some((variant) => opportunityMatchesReviewFilter(variant, attentionFilter, queueById.get(variant.id), duplicateIds));
    return matchesSearch && matchesStatus && matchesAttention;
  }), [attentionFilter, duplicateIds, families, queueById, search, status]);
  const filteredAcquired = useMemo(() => (acquired?.items ?? []).filter((candidate) => {
    const matchesSearch = !search.trim() || `${candidate.seed_name} ${candidate.seed_provider ?? ""} ${candidate.seed_country ?? ""}`.toLowerCase().includes(search.trim().toLowerCase());
    return matchesSearch && candidateMatchesReviewFilter(candidate, attentionFilter);
  }), [acquired, attentionFilter, search]);

  if (isRestoring) return <main className="page-width loading-page">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "admin") return <Navigate replace to="/dashboard" />;

  return (
    <main className="admin-page page-width" aria-busy={isLoading}>
      <section className="admin-catalogue-hero"><div><p className="eyebrow">Private scholarship review</p><h1>Choose a scholarship. Review one clear page.</h1><p>Degree routes are grouped together. Nothing is published until you explicitly approve it.</p></div><Link className="button button-quiet" to="/catalogue">View visitor catalogue</Link></section>
      {isLoading ? <div className="catalogue-message">Loading scholarship cards...</div> : null}
      {error ? <div className="catalogue-message error-message" role="alert"><h2>We could not load the review catalogue.</h2><p>{error}</p><button className="button button-quiet" type="button" onClick={() => load()}>Try again</button></div> : null}
      {!isLoading && !error ? <>
        <section className="admin-summary"><div><strong>{families.length}</strong><span>scholarship families</span></div><div><strong>{queue?.pagination.total ?? 0}</strong><span>records needing review</span></div><div><strong>{filteredAcquired.length}</strong><span>matching acquisitions</span></div></section>
        <section className="admin-catalogue-toolbar" aria-label="Filter scholarship cards">
          <div className="admin-search-control">
            <label>
              <span className="sr-only">Search scholarships</span>
              <input
                type="search"
                name="admin-scholarship-query"
                autoComplete="off"
                data-1p-ignore="true"
                data-lpignore="true"
                value={search}
                onChange={(event) => setSearch(sanitizeScholarshipSearch(event.target.value))}
                placeholder="Search scholarship, provider, or country"
              />
            </label>
            {search ? <button type="button" onClick={() => setSearch("")} aria-label="Clear scholarship search">Clear</button> : null}
          </div>
          <label><span className="sr-only">Record status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">All statuses</option><option value="draft">Draft</option><option value="active">Active</option><option value="expired">Expired</option><option value="archived">Archived</option></select></label>
          <label><span className="sr-only">Readiness filter</span><select value={attentionFilter} onChange={(event) => setAttentionFilter(event.target.value as ReviewAttentionFilter)}><option value="all">All readiness states</option><option value="complete">Complete</option><option value="missing_funding">Missing funding</option><option value="missing_deadline">Missing deadline</option><option value="missing_eligibility">Missing eligibility</option><option value="conflicts">Conflicts</option><option value="duplicates">Duplicates</option><option value="stale_sources">Stale sources</option><option value="failed_acquisition">Failed acquisition</option></select></label>
          <span>{filtered.length} scholarship{filtered.length === 1 ? "" : "s"} · {filteredAcquired.length} acquisition{filteredAcquired.length === 1 ? "" : "s"}</span>
        </section>
        {filtered.length ? <section className="opportunity-grid admin-scholarship-grid" aria-label="Scholarships to review">{filtered.map((family) => <ScholarshipAdminCard key={family.key} family={family} />)}</section> : <div className="catalogue-message"><h2>No scholarship records match.</h2><p>Try another readiness filter or clear the search.</p></div>}
        {filteredAcquired.length ? <section className="review-section"><div className="result-heading"><div><p className="eyebrow">Acquired sources</p><h2>Evidence awaiting a final catalogue decision</h2></div><p className="result-count">{filteredAcquired.length} candidates</p></div><div className="advanced-card-grid">{filteredAcquired.map((candidate) => <AcquiredCandidateCard key={candidate.id} candidate={candidate} />)}</div></section> : null}
        <details className="admin-advanced-tools">
          <summary><span>Advanced tools</span><small>Acquisition, import, and data-quality diagnostics</small></summary>
          <div className="admin-advanced-content">
            <DuplicateResolutionPanel suggestions={duplicates ?? { items: [], pagination: { total: 0, limit: 100, offset: 0, count: 0, has_next: false, has_previous: false } }} onChanged={() => load(0)} />
            <DirectUrlIngestionPanel onChanged={() => load(0)} />
            <div className="admin-layout"><section className="admin-panel"><p className="eyebrow">Data quality</p><h2>Automated diagnostic signals</h2><IssueList issues={issues?.items ?? []} /><PageControls offset={issueOffset} total={issues?.pagination.total ?? 0} limit={issues?.pagination.limit ?? 20} hasNext={issues?.pagination.has_next ?? false} onChange={(nextOffset) => load(nextOffset)} /></section><ImportPanel onChanged={() => load(0)} /></div>
          </div>
        </details>
      </> : null}
    </main>
  );
}
