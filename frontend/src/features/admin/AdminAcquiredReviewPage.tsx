import { Link, Navigate, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import { formatDate } from "../catalogue/catalogue";
import { getAcquiredCandidateReview } from "./admin";
import type { AcquiredCandidateReview, CandidateReviewFact } from "./types";

function readable(value: string): string {
  return value.replaceAll("_", " ");
}

export function candidateReviewFactValue(fact: CandidateReviewFact): string {
  const value = Object.values(fact.value).find((item) => item !== null && item !== undefined);
  if (Array.isArray(value)) return value.join(", ");
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  return "Unknown";
}

export function candidateScopeLabel(fact: CandidateReviewFact): string {
  const labels = Object.entries(fact.scope)
    .filter(([, value]) => Boolean(value))
    .map(([key, value]) => `${readable(key.replace(/_key$/, ""))}: ${value}`);
  return labels.length ? labels.join(" · ") : "Scholarship-wide";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function blockerMessage(code: string): string {
  if (code === "ai_ingestion_disabled") return "Structured extraction is waiting because Catalogue AI is disabled.";
  if (code === "direct_source_bundle_incomplete") return "One or more supplied sources could not be verified and fetched as official evidence.";
  if (code === "candidate_only_complete") return "Source acquisition completed in evidence-only mode; extraction has not run.";
  return readable(code);
}

function AcquiredReview({ review }: { review: AcquiredCandidateReview }) {
  const { candidate, projection } = review;
  const { readiness } = projection;
  const officialSources = projection.sources.filter((source) => source.is_official);
  const artifactCount = projection.sources.reduce((total, source) => total + source.artifacts.length, 0);
  const incompleteObjectives = Object.entries(projection.objective_coverage).filter(([, state]) => !["complete", "not_applicable"].includes(state));
  const bundleGaps = stringList(projection.acquisition_bundle.gaps);
  const attention = [
    ...readiness.blockers.map((item) => ({ level: "blocker", value: item })),
    ...projection.warnings.map((item) => ({ level: "warning", value: item })),
    ...projection.conflicts.map((item) => ({ level: "conflict", value: item })),
    ...projection.rejected_claims.map((item) => ({ level: "rejected", value: item })),
  ];

  return <>
    <section className="detail-hero review-detail-hero"><div><p className="eyebrow">Acquired evidence · private review</p><h1>{candidate.seed_name}</h1><p className="provider-name">{candidate.seed_provider ?? "Provider not supplied"}{candidate.seed_country ? ` · ${candidate.seed_country}` : ""}</p><p className="seed-hint-note">The heading contains operator seed hints. Only the facts below are evidence-backed.</p></div><div className="tag-list detail-tags"><span>{readable(candidate.status)}</span><span>{officialSources.length} official source{officialSources.length === 1 ? "" : "s"}</span><span>{artifactCount} saved artifact{artifactCount === 1 ? "" : "s"}</span></div></section>

    <section className={`review-readiness ${readiness.ready ? "is-ready" : "is-blocked"}`}><div><p className="eyebrow">Backend readiness</p><h2>{readiness.ready ? "Complete for human review" : "Blocked"}</h2></div><div><p>{readiness.supported_mandatory_count} of {readiness.mandatory_count} mandatory objectives are supported. Source freshness is {readiness.source_freshness}.</p><small>Evaluated {formatDate(readiness.evaluated_at)}</small></div></section>

    <section className="review-scan-summary"><div className="review-summary-found"><strong>{projection.proposed_facts.length}</strong><span>evidence-backed facts</span></div><div className="review-summary-missing"><strong>{readiness.mandatory_count - readiness.supported_mandatory_count}</strong><span>objectives incomplete</span></div><div className="review-summary-critical"><strong>{projection.conflicts.length}</strong><span>conflicts</span></div><div><strong>{projection.duplicate_opportunity_ids.length}</strong><span>duplicate suggestions</span></div><div><strong>{artifactCount}</strong><span>saved artifacts</span></div></section>

    {readiness.blockers.length || incompleteObjectives.length ? <section className="review-gap-strip"><strong>Publication blockers</strong><div>{readiness.blockers.map((item) => <span key={item}>{blockerMessage(item)}</span>)}{incompleteObjectives.map(([objective, state]) => <span key={objective}>{readable(objective)}: {readable(state)}</span>)}</div></section> : null}

    <section className="review-sources acquired-fact-review"><div><p className="eyebrow">Resolved catalogue facts</p><h2>Values with exact source evidence</h2><p>Every proposed field carries source, scope, freshness, and extraction lineage.</p></div><div className="review-source-list">{projection.proposed_facts.length ? projection.proposed_facts.map((fact) => <article key={`${fact.entity_type}-${fact.entity_key}-${fact.field_path}-${fact.evidence.block_id}`}><div className="review-source-head"><div><span className="review-source-status is-verified">{fact.authority_tier}</span><h3>{readable(fact.entity_type)} · {readable(fact.field_path)}</h3></div><a className="button button-quiet" href={fact.source_url} target="_blank" rel="noreferrer">Open official source ↗</a></div><p className="review-fact-value"><strong>{candidateReviewFactValue(fact)}</strong></p><blockquote>{fact.evidence.text}</blockquote><dl className="review-evidence-meta"><div><dt>Source</dt><dd>{fact.source_title}</dd></div><div><dt>Scope</dt><dd>{candidateScopeLabel(fact)}</dd></div><div><dt>Checked</dt><dd>{formatDate(fact.source_checked_at)}</dd></div><div><dt>Evidence</dt><dd>{fact.evidence.block_id} · offsets {fact.evidence.start_offset}–{fact.evidence.end_offset}</dd></div></dl>{fact.extraction ? <details className="inline-lineage"><summary>Extraction lineage</summary><p>{readable(fact.extraction.objective)} · {fact.extraction.provider} / {fact.extraction.model} · schema {fact.extraction.schema_version} · prompt {fact.extraction.prompt_hash.slice(0, 12)}</p></details> : null}</article>) : <p className="admin-empty">No claims have passed evidence validation yet.</p>}</div></section>

    {attention.length ? <section className="review-attention"><div><p className="eyebrow">Needs attention</p><h2>Why this record is blocked or warned</h2></div><ul>{attention.map((item, index) => <li key={`${item.level}-${item.value}-${index}`}><span className={`severity ${item.level === "warning" ? "severity-medium" : "severity-high"}`}>{item.level}</span><div><strong>{readable(item.value)}</strong>{item.level === "blocker" ? <p>{blockerMessage(item.value)}</p> : null}</div></li>)}</ul></section> : null}

    <section className="review-secondary-disclosures" aria-label="Review lineage and diagnostics">
      <details open><summary>Source artifacts and routing ({artifactCount})</summary><div className="review-disclosure-body">{projection.sources.map((source) => <article key={source.id}><h3>{source.title}</h3><p><a href={source.final_url ?? source.url} target="_blank" rel="noreferrer">{source.final_url ?? source.url}</a></p><small>{readable(source.status)} · checked {formatDate(source.checked_at)}{source.failure_code ? ` · ${readable(source.failure_code)}` : ""}</small>{source.artifacts.map((artifact) => <div className="lineage-row" key={artifact.id}><strong>{readable(artifact.acquisition_role)}</strong><span>{artifact.content_type} · {artifact.extraction_method} · {artifact.evidence_block_count} evidence blocks · hash {artifact.content_hash.slice(0, 12)}</span></div>)}{source.routing.map((route) => <div className="lineage-row" key={`${route.classifier_version}-${route.role}-${route.cycle}`}><strong>{readable(route.role)} / {readable(route.cycle)}</strong><span>{route.authority_tier} · {route.applicable_objectives.map(readable).join(", ") || "no objectives"}{route.requires_manual_review ? " · manual review required" : ""}</span></div>)}</article>)}</div></details>
      <details><summary>Extraction attempts ({projection.extraction_attempts.length})</summary><div className="review-disclosure-body">{projection.extraction_attempts.map((attempt) => <div className="lineage-row" key={attempt.id}><strong>{readable(attempt.status)} · {attempt.schema_version}</strong><span>{attempt.provider} / {attempt.model} · {attempt.input_tokens + attempt.output_tokens} tokens · {attempt.latency_ms} ms · {formatDate(attempt.created_at)}{attempt.error_code ? ` · ${readable(attempt.error_code)}` : ""}</span></div>)}</div></details>
      <details><summary>Acquisition bundle ({bundleGaps.length} gaps)</summary><div className="review-disclosure-body"><p>{projection.acquisition_bundle.complete ? "The required source-role bundle is complete." : "The bundle is reviewable but incomplete."}</p>{bundleGaps.length ? <ul>{bundleGaps.map((gap) => <li key={gap}>{readable(gap)}</li>)}</ul> : null}</div></details>
      <details><summary>Conflicts, duplicates, and warnings ({attention.length})</summary><div className="review-disclosure-body"><ul>{projection.conflicts.map((item) => <li key={`conflict-${item}`}>Conflict: {item}</li>)}{projection.duplicate_opportunity_ids.map((item) => <li key={item}>Possible duplicate opportunity: {item}</li>)}{projection.warnings.map((item) => <li key={`warning-${item}`}>Warning: {readable(item)}</li>)}</ul>{!projection.conflicts.length && !projection.duplicate_opportunity_ids.length && !projection.warnings.length ? <p>No conflicts, duplicates, or warnings.</p> : null}</div></details>
      <details><summary>Decision and audit history ({projection.decision_history.length + projection.audit_history.length})</summary><div className="review-disclosure-body">{projection.decision_history.map((item) => <div className="lineage-row" key={`${item.proposal_hash}-${item.created_at}`}><strong>{readable(item.action)} · {readable(item.prior_candidate_status)}</strong><span>{item.reason} · {formatDate(item.created_at)} · proposal {item.proposal_hash.slice(0, 12)}</span></div>)}{projection.audit_history.map((item) => <div className="lineage-row" key={`${item.integrity_hash}-${item.created_at}`}><strong>{readable(item.action)}</strong><span>{item.reason ?? "No reviewer note"} · {formatDate(item.created_at)} · audit {item.integrity_hash.slice(0, 12)}</span></div>)}{!projection.decision_history.length && !projection.audit_history.length ? <p>No review decisions have been recorded.</p> : null}</div></details>
    </section>
  </>;
}

export function AdminAcquiredReviewPage() {
  const { candidateId } = useParams();
  const { user, isRestoring } = useAuth();
  const { data, error, isLoading, reload } = useServerQuery<AcquiredCandidateReview>(candidateId ?? "missing-candidate", (signal) => getAcquiredCandidateReview(candidateId!, signal), Boolean(candidateId && user?.role === "admin"));
  if (isRestoring) return <main className="page-width loading-page">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "admin") return <Navigate replace to="/dashboard" />;
  return <main className="detail-page review-detail-page page-width" aria-live="polite" aria-busy={isLoading}><Link className="back-link" to="/admin">← Back to review catalogue</Link>{isLoading ? <div className="catalogue-message">Loading acquired evidence...</div> : null}{!isLoading && error ? <div className="catalogue-message error-message" role="alert"><h1>We could not load this acquired record.</h1><p>{error instanceof Error ? error.message : "Please try again."}</p><button className="button button-quiet" type="button" onClick={reload}>Try again</button></div> : null}{!isLoading && !error && data ? <AcquiredReview review={data} /> : null}</main>;
}
