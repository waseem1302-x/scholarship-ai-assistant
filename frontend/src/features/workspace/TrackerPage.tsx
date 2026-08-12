import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { formatDate } from "../catalogue/catalogue";
import { applicationStatuses, type SavedOpportunity } from "./types";
import { deleteSaved, getSaved, humanize, updateSaved } from "./workspace";

function deadlineInput(value: string | null): string { return value ? value.slice(0, 10) : ""; }

function TrackerCard({ item, onChanged }: { item: SavedOpportunity; onChanged: () => void }) {
  const [status, setStatus] = useState(item.status);
  const [notes, setNotes] = useState(item.personal_notes ?? "");
  const [deadline, setDeadline] = useState(deadlineInput(item.personal_deadline));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() { setIsSaving(true); setError(null); try { await updateSaved(item.id, { status, personal_notes: notes.trim() || null, personal_deadline: deadline ? `${deadline}T00:00:00Z` : null }); onChanged(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to update this tracker item."); } finally { setIsSaving(false); } }
  async function remove() { if (!window.confirm(`Remove ${item.opportunity.name} from your tracker?`)) return; setIsSaving(true); try { await deleteSaved(item.id); onChanged(); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to remove this tracker item."); setIsSaving(false); } }
  return <article className="tracker-card"><div className="tracker-card-header"><div><h2>{item.opportunity.name}</h2><p>{item.opportunity.country} · Official deadline {formatDate(item.opportunity.application_deadline)}</p></div><Link className="detail-link" to={`/catalogue/${item.opportunity.id}`}>Opportunity details</Link></div>
    <div className="tracker-fields"><label>Status<select value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>{applicationStatuses.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Personal deadline<input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label><label className="wide">Notes<textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What do you need to do next?" /></label></div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}<div className="card-actions"><button className="button button-primary" type="button" onClick={save} disabled={isSaving}>{isSaving ? "Saving..." : "Save update"}</button><button className="button button-danger" type="button" onClick={remove} disabled={isSaving}>Remove</button></div>
  </article>;
}

export function TrackerPage() {
  const { user, isRestoring } = useAuth();
  const [items, setItems] = useState<SavedOpportunity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = () => { setIsLoading(true); setError(null); void getSaved().then(setItems).catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Unable to load your tracker.")).finally(() => setIsLoading(false)); };
  useEffect(() => { if (user?.role === "student") load(); }, [user]);
  if (isRestoring) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "student") return <Navigate replace to="/dashboard" />;
  return <main className="workspace-tool page-width" aria-busy={isLoading}><section className="tool-header"><div><p className="eyebrow">Application tracker</p><h1>Turn research into a clear next step.</h1><p className="lead">Keep your status, personal deadline, and working notes together. This is private to your student account.</p></div><Link className="button button-quiet" to="/catalogue">Browse opportunities</Link></section>
    {isLoading ? <div className="catalogue-message">Loading your tracker...</div> : null}{error ? <div className="catalogue-message error-message" role="alert"><h2>We could not load your tracker.</h2><p>{error}</p><button className="button button-quiet" onClick={load}>Try again</button></div> : null}
    {!isLoading && !error && !items.length ? <div className="catalogue-message"><h2>Your tracker is empty.</h2><p>Save an opportunity from its detail page when you are ready to start your application plan.</p><Link className="button button-primary" to="/catalogue">Explore verified opportunities</Link></div> : null}<div className="tracker-list">{items.map((item) => <TrackerCard key={item.id} item={item} onChanged={load} />)}</div>
  </main>;
}
