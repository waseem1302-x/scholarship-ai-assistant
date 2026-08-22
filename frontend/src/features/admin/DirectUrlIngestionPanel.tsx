import { type FormEvent, useState } from "react";

import { acquireOfficialUrl } from "./admin";
import type { IngestionCandidate, IngestionRun, OpportunityGraph } from "./types";

export function DirectUrlIngestionPanel({ onChanged }: { onChanged: () => void }) {
  const [url, setUrl] = useState("");
  const [supportingUrls, setSupportingUrls] = useState<string[]>([]);
  const [targetName, setTargetName] = useState("");
  const [university, setUniversity] = useState("");
  const [password, setPassword] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [run, setRun] = useState<IngestionRun | null>(null);
  const [candidate, setCandidate] = useState<IngestionCandidate | null>(null);
  const [graph, setGraph] = useState<OpportunityGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await acquireOfficialUrl(
        url,
        targetName,
        dryRun,
        password,
        supportingUrls.filter((item) => item.trim()).map((item) => item.trim()),
        university,
      );
      setRun(result.run);
      setCandidate(result.candidate);
      setGraph(result.graph);
      setPassword("");
      onChanged();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to acquire the official source.");
    } finally {
      setLoading(false);
    }
  }

  return <section className="admin-panel direct-url-panel">
    <p className="eyebrow">Official URL acquisition</p>
    <h2>Build a cited scholarship record.</h2>
    <form className="direct-url-form" onSubmit={submit}>
      <label className="wide">Official HTTPS URL<input type="url" required value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://www.mext.go.jp/..." /></label>
      <fieldset className="wide supporting-url-fieldset">
        <legend>Supporting official URLs</legend>
        <div className="supporting-url-list">
          {supportingUrls.map((item, index) => <div key={index}>
            <label className="sr-only" htmlFor={`supporting-url-${index}`}>Supporting official URL {index + 1}</label>
            <input id={`supporting-url-${index}`} type="url" required value={item} onChange={(event) => setSupportingUrls((current) => current.map((value, itemIndex) => itemIndex === index ? event.target.value : value))} placeholder="https://www.mext.go.jp/...pdf" />
            <button className="button button-quiet" type="button" onClick={() => setSupportingUrls((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>
          </div>)}
          {supportingUrls.length < 9 ? <button className="button button-quiet supporting-url-add" type="button" onClick={() => setSupportingUrls((current) => [...current, ""])}>Add supporting URL</button> : null}
        </div>
      </fieldset>
      <label>Expected name (optional)<input value={targetName} onChange={(event) => setTargetName(event.target.value)} placeholder="MEXT Scholarship" /></label>
      <label>Expected university (optional)<input value={university} onChange={(event) => setUniversity(event.target.value)} placeholder="Canonical university name" /></label>
      <label>Administrator password<input type="password" required autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <label className="direct-url-toggle"><input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} /> Validate without creating a draft</label>
      <button className="button button-primary" disabled={loading}>{loading ? "Acquiring..." : "Acquire official record"}</button>
    </form>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    {run && candidate ? <div className="acquisition-result" role="status">
      <strong>{candidate.status.replaceAll("_", " ")}</strong>
      <span>Run {run.status.replaceAll("_", " ")}</span>
      {candidate.validation_errors.map((item) => <p key={item}>{item.replaceAll("_", " ")}</p>)}
      {candidate.conflicts.map((item) => <p key={item}>{item.replaceAll("_", " ")}</p>)}
      {candidate.sources?.length ? <ul className="source-bundle-result">{candidate.sources.map((source) => <li key={source.id}>
        <strong>{source.source_role}</strong>
        <span>{source.failure_code?.replaceAll("_", " ") ?? (source.is_official ? "official" : "unverified")}</span>
        <a href={source.final_url ?? source.url} target="_blank" rel="noreferrer">{new URL(source.final_url ?? source.url).hostname}</a>
      </li>)}</ul> : null}
    </div> : null}
    {graph ? <div className="graph-review">
      <div><strong>{graph.tracks.length}</strong><span>routes</span></div>
      <div><strong>{graph.funding.length}</strong><span>funding facts</span></div>
      <div><strong>{graph.institutions.length}</strong><span>institutions</span></div>
      <div><strong>{graph.citations.length}</strong><span>citations</span></div>
      <p className="graph-degree-scope">Degree scope: {graph.degree_levels.map((level) => level.replaceAll("_", " ")).join(", ")}</p>
      <ul>{graph.tracks.map((track) => <li key={track.id}><strong>{track.name}</strong><span>{track.track_type.replaceAll("_", " ")}</span></li>)}</ul>
      <section><h3>Field citations</h3>{graph.citations.map((citation) => <article key={citation.id}><strong>{citation.entity_type} · {citation.field_path}</strong><p>{citation.excerpt}</p><a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_title}</a></article>)}</section>
    </div> : null}
  </section>;
}
