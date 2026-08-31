import { useEffect, useState } from "react";

import {
  getCatalogueCandidateObservability,
  getCatalogueCandidates,
  getCatalogueIngestionRuns,
  getCatalogueRunObservability,
} from "./admin";
import type {
  CatalogueCandidateObservability,
  CatalogueRunObservability,
  IngestionCandidate,
  IngestionRun,
} from "./types";

function label(value: string) {
  return value.replaceAll("_", " ");
}

export function CatalogueIngestionObservabilityPanel() {
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<CatalogueRunObservability | null>(null);
  const [candidates, setCandidates] = useState<IngestionCandidate[]>([]);
  const [candidate, setCandidate] = useState<CatalogueCandidateObservability | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    void getCatalogueIngestionRuns(controller.signal)
      .then((response) => {
        setRuns(response.items);
        setRunId(response.items[0]?.id ?? "");
      })
      .catch((requestError: unknown) => {
        if (!(requestError instanceof DOMException && requestError.name === "AbortError")) {
          setError(requestError instanceof Error ? requestError.message : "Unable to load ingestion runs.");
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!runId) {
      setRun(null);
      setCandidates([]);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setCandidate(null);
    void Promise.all([
      getCatalogueRunObservability(runId, controller.signal),
      getCatalogueCandidates(runId, controller.signal),
    ])
      .then(([runResponse, candidateResponse]) => {
        setRun(runResponse);
        setCandidates(candidateResponse.items);
      })
      .catch((requestError: unknown) => {
        if (!(requestError instanceof DOMException && requestError.name === "AbortError")) {
          setError(requestError instanceof Error ? requestError.message : "Unable to inspect this run.");
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [runId]);

  async function inspectCandidate(candidateId: string) {
    setLoading(true);
    setError(null);
    try {
      setCandidate(await getCatalogueCandidateObservability(candidateId));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to inspect this candidate.");
    } finally {
      setLoading(false);
    }
  }

  const attemptCount = run
    ? Object.values(run.provider_attempt_states).reduce((sum, count) => sum + count, 0)
    : 0;
  return <section className="admin-panel catalogue-observability-panel" aria-busy={loading}>
    <p className="eyebrow">Private ingestion operations</p>
    <h2>Inspect coverage, provider accounting, and review readiness.</h2>
    <label>Ingestion run<select value={runId} onChange={(event) => setRunId(event.target.value)}>
      <option value="">Select a run</option>
      {runs.map((item) => <option key={item.id} value={item.id}>{item.id.slice(0, 8)} · {label(item.status)}</option>)}
    </select></label>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    {run ? <>
      <div className="admin-summary">
        <div><strong>{run.costs.upper_bound}</strong><span>cost upper bound</span></div>
        <div><strong>{attemptCount}</strong><span>provider attempts</span></div>
        <div><strong>{run.circuits.filter((item) => item.state !== "closed").length}</strong><span>open circuits</span></div>
      </div>
      <p>{run.dry_run ? "Dry run · publication disabled" : "Private review run"} · kill switch {run.kill_switch_enabled ? "enabled" : "disabled"}</p>
      <ul className="issue-list">{candidates.map((item) => <li key={item.id}>
        <span className="severity severity-medium">{label(item.status)}</span>
        <div><strong>{item.id.slice(0, 8)}</strong><p>{item.validation_errors.length} validation gaps · {item.conflicts.length} conflicts</p></div>
        <button className="button button-quiet" type="button" onClick={() => void inspectCandidate(item.id)}>Inspect</button>
      </li>)}</ul>
    </> : null}
    {candidate ? <section className="acquisition-result" aria-label="Candidate observability">
      <h3>Scoped completeness</h3>
      <p>{candidate.topology.nodes.length} topology nodes · {candidate.source_count} sources · lease {candidate.lease.is_active ? "active" : "inactive"}</p>
      {candidate.unresolved_branches.length ? <ul>{candidate.unresolved_branches.map((branch) => <li key={`${branch.scope_node_id}:${branch.objective}`}>
        <strong>{label(branch.objective)} · {label(branch.state)}</strong>
        <span>{label(branch.reason)}</span>
        {branch.missing_frontier_reasons.map((reason) => <small key={reason}>{label(reason)}</small>)}
      </li>)}</ul> : <p>All recorded coverage branches are resolved.</p>}
      <p>{candidate.provider_attempts.length} provider attempts · {candidate.cache_decisions.length} cache decisions · review {candidate.review ? label(candidate.review.state) : "not submitted"}</p>
    </section> : null}
  </section>;
}
