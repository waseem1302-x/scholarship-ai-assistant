import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import { formatDate } from "../catalogue/catalogue";
import { ScholarshipDetailView, type ScholarshipDetailFamily } from "../catalogue/ScholarshipDetailView";
import { applyReviewAction, getAdminOpportunityFamily, recordSourceCheck, reverifySource } from "./admin";
import type { AdminOpportunityFamily, ReviewAction, ReviewQueueItem } from "./types";

function ReviewOverview({ item }: { item: ReviewQueueItem }) {
  const { publication_readiness: readiness } = item;

  return (
    <section className={`admin-review-overview ${readiness.ready ? "is-clear" : "has-blockers"}`} aria-label="Review status">
      <div className="admin-review-verdict">
        <span>{readiness.ready ? "Complete" : "Blocked"}</span>
        <strong>{readiness.ready ? "Backend publication gate passed" : `${readiness.blocking_reasons.length} publication blocker${readiness.blocking_reasons.length === 1 ? "" : "s"}`}</strong>
        <p>{readiness.ready ? "Compare the record with its official evidence before publishing." : "Publishing is locked until the backend readiness policy passes."}</p>
      </div>
      <div className="admin-review-metrics">
        <div><strong>{readiness.supported_required_count}/{readiness.required_count}</strong><span>mandatory checks supported</span></div>
        <div><strong>{readiness.warnings.length}</strong><span>warnings</span></div>
        <div><strong>{item.opportunity.verification_freshness.replaceAll("_", " ")}</strong><span>source freshness</span></div>
      </div>
      {readiness.blocking_reasons.length || readiness.warnings.length || item.reasons.length ? (
        <details className="review-issues-disclosure">
          <summary>See everything the system says needs attention</summary>
          <ul>
            {readiness.blocking_reasons.map((reason) => <li key={`blocker-${reason.field_path}-${reason.reason_code}`}><span className="severity severity-high">blocker</span><div><strong>{reason.reason_code.replaceAll("_", " ")}</strong><p>{reason.message}</p></div></li>)}
            {readiness.warnings.map((warning) => <li key={`warning-${warning.field_path}-${warning.reason_code}`}><span className="severity severity-medium">warning</span><div><strong>{warning.reason_code.replaceAll("_", " ")}</strong><p>{warning.message}</p></div></li>)}
            {item.reasons.map((reason) => <li key={`${reason.code}-${reason.source_id ?? "record"}`}><span className={`severity severity-${reason.severity}`}>{reason.severity}</span><div><strong>{reason.code.replaceAll("_", " ")}</strong><p>{reason.message}</p></div></li>)}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

function AdditionalEvidence({ item }: { item: ReviewQueueItem }) {
  if (item.opportunity.sources.length <= 1) return null;
  return (
    <section className="review-sources">
      <div><p className="eyebrow">Supporting evidence</p><h2>All official sources for this route</h2></div>
      <div className="review-source-list">
        {item.opportunity.sources.map((source) => (
          <article key={source.id}>
            <div className="review-source-head"><div><span className={`review-source-status ${source.verification_status === "officially_verified" ? "is-verified" : "needs-review"}`}>{source.verification_status.replaceAll("_", " ")}</span><h3>{source.title}</h3></div><a className="button button-quiet" href={source.url} target="_blank" rel="noreferrer">Open source ↗</a></div>
            <p>{source.relevant_excerpt}</p>
            <small>Checked {formatDate(source.last_verified_at)} · hash {source.content_hash ? source.content_hash.slice(0, 12) : "not stored"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ReviewActionDock({ item, reload }: { item: ReviewQueueItem; reload: () => void }) {
  const [notes, setNotes] = useState("");
  const [password, setPassword] = useState("");
  const [sourceId, setSourceId] = useState(item.opportunity.source.id);
  const [sourceHash, setSourceHash] = useState("");
  const [sourceSummary, setSourceSummary] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const readiness = item.publication_readiness;

  useEffect(() => {
    setSourceId(item.opportunity.source.id);
    setNotes("");
    setMessage(null);
    setError(null);
  }, [item.opportunity.id, item.opportunity.source.id]);

  async function run(operation: () => Promise<void>, success: string) {
    setIsSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      await operation();
      setPassword("");
      setMessage(success);
      reload();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to record this decision.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function decide(action: ReviewAction, label: string, notesRequired = false) {
    if (notesRequired && !notes.trim()) {
      setError(`Add a short reviewer note before choosing ${label.toLowerCase()}.`);
      return;
    }
    if (!window.confirm(`${label} “${item.opportunity.name}”? This decision applies only to the selected study route.`)) return;
    void run(() => applyReviewAction(item.opportunity.id, action, sourceId, notes, password), `${label} decision recorded.`);
  }

  function submitSourceCheck() {
    const normalizedHash = sourceHash.trim();
    if (normalizedHash && !/^[a-fA-F0-9]{32,64}$/.test(normalizedHash)) {
      setError("A source content hash must contain 32 to 64 hexadecimal characters.");
      return;
    }
    if (!window.confirm(`Record this source check for “${item.opportunity.name}”?`)) return;
    void run(async () => {
      await recordSourceCheck(sourceId, normalizedHash, sourceSummary, password);
      setSourceHash("");
      setSourceSummary("");
    }, "Source check recorded.");
  }

  return (
    <section className="admin-action-dock" aria-label="Reviewer decision">
      <div className="admin-action-copy"><p className="eyebrow">Your decision</p><h2>Approve, pause, or reject this route</h2><p>Nothing happens automatically. Every action needs your password and is written to the audit log.</p></div>
      <div className="admin-decision-fields">
        <label>Reviewer note<textarea rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="What did you verify, or what is still missing?" /></label>
        <label>Administrator password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Required for any decision" /></label>
      </div>
      {!readiness.ready ? <p className="publish-lock" role="status">Publish locked by {readiness.blocking_reasons.length} backend readiness check{readiness.blocking_reasons.length === 1 ? "" : "s"}. Reloading after any rejected action will refresh this verdict.</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {message ? <p className="form-success" role="status">{message}</p> : null}
      <div className="admin-primary-actions">
        <button className="button button-publish" type="button" onClick={() => decide("publish", "Publish")} disabled={isSubmitting || !readiness.ready}>Publish</button>
        <button className="button button-hold" type="button" onClick={() => decide("hold_for_review", "Hold", true)} disabled={isSubmitting}>Hold</button>
        <button className="button button-danger" type="button" onClick={() => decide("archive", "Reject and archive", true)} disabled={isSubmitting}>Reject</button>
      </div>
      <details className="admin-more-actions">
        <summary>More review and source tools</summary>
        <div className="admin-more-grid">
          <label>Evidence source<select value={sourceId} onChange={(event) => setSourceId(event.target.value)}>{item.opportunity.sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>
          <div className="admin-secondary-actions">
            <button className="button button-quiet" type="button" onClick={() => decide("flag_conflict", "Flag conflict", true)} disabled={isSubmitting}>Flag conflict</button>
            <button className="button button-quiet" type="button" onClick={() => decide("request_recheck", "Request recheck", true)} disabled={isSubmitting}>Request recheck</button>
            <button className="button button-quiet" type="button" onClick={() => decide("resolve_conflict", "Resolve conflict", true)} disabled={isSubmitting}>Resolve conflict</button>
            <button className="button button-quiet" type="button" onClick={() => decide("expire", "Mark expired", true)} disabled={isSubmitting}>Mark expired</button>
          </div>
          <label>Observed content hash (optional)<input value={sourceHash} onChange={(event) => setSourceHash(event.target.value)} placeholder="SHA-256 or comparable hash" /></label>
          <label>Source check summary (optional)<textarea rows={2} value={sourceSummary} onChange={(event) => setSourceSummary(event.target.value)} placeholder="What changed on the official page?" /></label>
          <div className="admin-secondary-actions"><button className="button button-quiet" type="button" onClick={submitSourceCheck} disabled={isSubmitting}>Record source check</button><button className="button button-quiet" type="button" onClick={() => void run(() => reverifySource(item.opportunity.id, sourceId, notes, password), "Source reverified.")} disabled={isSubmitting}>Reverify source</button></div>
        </div>
      </details>
    </section>
  );
}

export function AdminReviewPage() {
  const { opportunityId } = useParams();
  const { user, isRestoring } = useAuth();
  const [activeId, setActiveId] = useState(opportunityId ?? "");
  const { data: family, error, isLoading, reload } = useServerQuery<AdminOpportunityFamily>(
    opportunityId ?? "missing-opportunity",
    (signal) => getAdminOpportunityFamily(opportunityId!, signal),
    Boolean(opportunityId && user?.role === "admin"),
  );

  useEffect(() => {
    if (family && !family.variants.some((variant) => variant.opportunity.id === activeId)) {
      setActiveId(family.variants[0]?.opportunity.id ?? "");
    }
  }, [activeId, family]);

  const selected = family?.variants.find((variant) => variant.opportunity.id === activeId) ?? family?.variants[0];
  const viewFamily = useMemo<ScholarshipDetailFamily | null>(() => family ? ({
    family_key: family.family_key,
    name: family.name,
    provider_name: family.provider_name,
    country: family.country,
    degree_levels: family.degree_levels,
    variants: family.variants.map((variant) => variant.opportunity),
  }) : null, [family]);

  if (isRestoring) return <main className="page-width loading-page">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "admin") return <Navigate replace to="/dashboard" />;

  return (
    <main className="detail-page review-detail-page page-width" aria-live="polite" aria-busy={isLoading}>
      <Link className="back-link" to="/admin">← Back to scholarship cards</Link>
      {isLoading ? <div className="catalogue-message">Loading the complete scholarship review...</div> : null}
      {!isLoading && error ? <div className="catalogue-message error-message" role="alert"><h1>We could not load this review.</h1><p>{error instanceof Error ? error.message : "Please try again."}</p><button className="button button-quiet" type="button" onClick={reload}>Try again</button></div> : null}
      {!isLoading && !error && viewFamily && selected ? (
        <ScholarshipDetailView
          family={viewFamily}
          activeId={selected.opportunity.id}
          onActiveIdChange={setActiveId}
          beforeDetails={<ReviewOverview item={selected} />}
          afterDetails={<><AdditionalEvidence item={selected} /><ReviewActionDock item={selected} reload={reload} /></>}
        />
      ) : null}
    </main>
  );
}
