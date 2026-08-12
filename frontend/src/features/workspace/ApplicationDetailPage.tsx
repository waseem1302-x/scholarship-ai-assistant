import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { formatDate } from "../catalogue/catalogue";
import type { Application, ApplicationEvent, ApplicationTask, CommandLifecycle } from "./types";
import {
  createApplicationDocument,
  createApplicationReminder,
  createApplicationTask,
  getApplication,
  getApplicationEvents,
  humanize,
  updateApplication,
  updateApplicationDocument,
  updateApplicationReminder,
  updateApplicationTask,
} from "./workspace";

const lifecycleSteps: CommandLifecycle[] = ["saved", "preparing", "ready_to_submit", "submitted", "decision_received", "accepted", "declined", "withdrawn"];
const taskCategories = ["document", "test", "recommendation", "funding", "official_verification", "personal"];
const transitions: Record<CommandLifecycle, CommandLifecycle[]> = {
  saved: ["preparing", "withdrawn"],
  preparing: ["saved", "ready_to_submit", "withdrawn"],
  ready_to_submit: ["preparing", "submitted", "withdrawn"],
  submitted: ["decision_received", "withdrawn"],
  decision_received: ["accepted", "declined", "withdrawn"],
  accepted: [], declined: [], withdrawn: [],
};

function localDateTime(value: string | null): string { return value ? value.slice(0, 16) : ""; }

export function ApplicationDetailPage() {
  const { applicationId } = useParams();
  const { user, isRestoring } = useAuth();
  const [application, setApplication] = useState<Application | null>(null);
  const [events, setEvents] = useState<ApplicationEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskCategory, setTaskCategory] = useState("personal");
  const [reminderAt, setReminderAt] = useState("");
  const [reminderMessage, setReminderMessage] = useState("");
  const [personalDeadline, setPersonalDeadline] = useState("");
  const [documentName, setDocumentName] = useState("");
  const [documentRequired, setDocumentRequired] = useState(true);

  const load = () => {
    if (!applicationId) return;
    setLoading(true); setError(null);
    void Promise.all([getApplication(applicationId), getApplicationEvents(applicationId)])
      .then(([current, history]) => {
        setApplication(current); setNotes(current.notes ?? ""); setPersonalDeadline(localDateTime(current.personal_deadline)); setEvents(history);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load this application."))
      .finally(() => setLoading(false));
  };
  useEffect(() => { if (user?.role === "student") load(); }, [applicationId, user]);

  async function perform(action: () => Promise<void>) {
    setActionError(null);
    try { await action(); }
    catch (reason) { setActionError(reason instanceof Error ? reason.message : "We could not save that change."); }
  }
  async function saveNotes() { if (!application) return; await updateApplication(application.id, { notes: notes.trim() || null, expected_version: application.version }); load(); }
  async function savePersonalDeadline() { if (!application) return; await updateApplication(application.id, { personal_deadline: personalDeadline ? new Date(personalDeadline).toISOString() : null, personal_deadline_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, expected_version: application.version }); load(); }
  async function setLifecycle(lifecycle: CommandLifecycle) { if (!application) return; await updateApplication(application.id, { lifecycle, expected_version: application.version }); load(); }
  async function setTaskStatus(task: ApplicationTask, status: string) { if (!application) return; await updateApplicationTask(application.id, task.id, { status, completion_evidence: status === "completed" ? "Marked complete by student" : null }); load(); }
  async function editTask(task: ApplicationTask) { if (!application) return; const title = window.prompt("Task title", task.title); if (!title?.trim()) return; const dueAt = window.prompt("Task deadline (YYYY-MM-DDTHH:mm), or leave blank", localDateTime(task.due_at)); const due = dueAt?.trim() ? new Date(dueAt).toISOString() : null; await updateApplicationTask(application.id, task.id, { title: title.trim(), due_at: due }); load(); }
  async function addTask(event: FormEvent) { event.preventDefault(); if (!application || !taskTitle.trim()) return; await createApplicationTask(application.id, { title: taskTitle.trim(), category: taskCategory }); setTaskTitle(""); load(); }
  async function addReminder(event: FormEvent) { event.preventDefault(); if (!application || !reminderAt) return; await createApplicationReminder(application.id, { scheduled_at: new Date(reminderAt).toISOString(), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, message: reminderMessage.trim() || null }); setReminderAt(""); setReminderMessage(""); load(); }
  async function dismissReminder(id: string) { if (!application) return; await updateApplicationReminder(application.id, id, { status: "cancelled" }); load(); }
  async function rescheduleReminder(id: string, scheduledAt: string) { if (!application) return; const next = window.prompt("Reminder time (YYYY-MM-DDTHH:mm)", localDateTime(scheduledAt)); if (!next?.trim()) return; await updateApplicationReminder(application.id, id, { status: "scheduled", scheduled_at: new Date(next).toISOString(), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }); load(); }
  async function addDocument(event: FormEvent) { event.preventDefault(); if (!application || !documentName.trim()) return; await createApplicationDocument(application.id, { name: documentName.trim(), is_required: documentRequired }); setDocumentName(""); setDocumentRequired(true); load(); }
  async function saveDocument(documentId: string, event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!application) return; const fields = new FormData(event.currentTarget); const date = (name: string) => { const value = String(fields.get(name) ?? "").trim(); return value ? new Date(value).toISOString() : null; }; const text = (name: string) => String(fields.get(name) ?? "").trim() || null; const size = text("size_bytes"); await updateApplicationDocument(application.id, documentId, { name: String(fields.get("name") ?? "").trim(), is_required: fields.get("is_required") === "on", file_name: text("file_name"), content_type: text("content_type"), size_bytes: size ? Number(size) : null, version_label: text("version_label"), expires_at: date("expires_at"), reviewed_at: date("reviewed_at"), is_complete: fields.get("is_complete") === "on" }); load(); }

  if (isRestoring) return <main className="page-width loading-page">Restoring your secure session…</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "student") return <Navigate replace to="/dashboard" />;
  if (loading) return <main className="workspace-tool page-width">Loading application workspace…</main>;
  if (error || !application) return <main className="workspace-tool page-width"><div className="catalogue-message error-message" role="alert"><h1>We could not load this application.</h1><p>{error}</p><Link className="button button-primary" to="/applications">Back to applications</Link></div></main>;

  return <main className="workspace-tool page-width">
    <Link className="back-link" to="/applications">← Application command centre</Link>
    <section className="application-detail-head"><div><p className="eyebrow">{humanize(application.lifecycle)}</p><h1>{application.opportunity.name}</h1><p>{application.opportunity.provider_name} · Official deadline {formatDate(application.official_deadline)} ({application.official_deadline_timezone})</p></div><a className="button button-quiet" href={application.opportunity.official_source_url} target="_blank" rel="noreferrer">Open official evidence</a></section>
    {actionError ? <p className="catalogue-message error-message" role="alert">{actionError}</p> : null}
    {application.deadline_urgency !== "upcoming" ? <p className="deadline-alert" role="status">Deadline is {humanize(application.deadline_urgency)}. Confirm the official source before acting.</p> : null}
    <section className="application-panel"><h2>Deadline timeline</h2><dl className="deadline-timeline"><div><dt>Official deadline</dt><dd>{formatDate(application.official_deadline)} ({application.official_deadline_timezone}) — {humanize(application.official_deadline_state)}</dd></div><div><dt>Your target deadline</dt><dd>{application.personal_deadline ? `${formatDate(application.personal_deadline)} (${application.personal_deadline_timezone})` : "Not set"}</dd></div></dl><form className="inline-form" onSubmit={(event) => { event.preventDefault(); void perform(savePersonalDeadline); }}><label>Set your target<input type="datetime-local" value={personalDeadline} onChange={(event) => setPersonalDeadline(event.target.value)} /></label><button className="button button-quiet" type="submit">Save target</button></form></section>
    <section className="application-panel"><h2>Lifecycle</h2><p className="muted-copy">Current: {humanize(application.lifecycle)}</p><div className="lifecycle-controls" aria-label="Application lifecycle">{lifecycleSteps.map((step) => <span key={step} className={application.lifecycle === step ? "lifecycle-current" : ""}>{humanize(step)}</span>)}</div>{transitions[application.lifecycle].length ? <div className="card-actions">{transitions[application.lifecycle].map((step) => <button key={step} className="button button-quiet" type="button" onClick={() => void perform(() => setLifecycle(step))}>Move to {humanize(step)}</button>)}</div> : <p className="muted-copy">This application lifecycle is final.</p>}</section>
    <div className="application-detail-grid">
      <section className="application-panel"><h2>Task board</h2><form className="inline-form" onSubmit={(event) => void perform(() => addTask(event))}><label>New task<input value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} required /></label><label>Category<select value={taskCategory} onChange={(event) => setTaskCategory(event.target.value)}>{taskCategories.map((category) => <option key={category}>{humanize(category)}</option>)}</select></label><button className="button button-primary" type="submit">Add task</button></form><div className="detail-task-list">{application.tasks.map((task) => <article className="detail-task" key={task.id}><div><strong>{task.title}</strong><small>{humanize(task.category)} · {task.is_generated ? "Source-generated" : "Personal"} · {task.due_at ? formatDate(task.due_at) : "No due date"}</small>{task.completion_evidence ? <small>Evidence: {task.completion_evidence}</small> : null}</div><div className="task-actions"><select aria-label={`Status for ${task.title}`} value={task.status} onChange={(event) => void perform(() => setTaskStatus(task, event.target.value))}><option value="todo">To do</option><option value="in_progress">In progress</option><option value="blocked">Blocked</option><option value="completed">Complete</option><option value="dismissed">Dismissed</option></select><button className="text-link" type="button" onClick={() => void perform(() => editTask(task))}>Edit</button></div></article>)}</div></section>
      <section className="application-panel"><h2>Reminders</h2><form className="inline-form" onSubmit={(event) => void perform(() => addReminder(event))}><label>When<input type="datetime-local" value={reminderAt} onChange={(event) => setReminderAt(event.target.value)} required /></label><label>Message<input value={reminderMessage} onChange={(event) => setReminderMessage(event.target.value)} /></label><button className="button button-primary" type="submit">Schedule</button></form>{application.reminders.length ? <ul className="compact-list">{application.reminders.map((reminder) => <li key={reminder.id}><span>{formatDate(reminder.scheduled_at)} · {reminder.status}{reminder.message ? ` — ${reminder.message}` : ""}</span>{["scheduled", "snoozed"].includes(reminder.status) ? <span className="task-actions"><button className="text-link" type="button" onClick={() => void perform(() => rescheduleReminder(reminder.id, reminder.scheduled_at))}>Reschedule</button><button className="text-link" type="button" onClick={() => void perform(() => dismissReminder(reminder.id))}>Dismiss</button></span> : null}</li>)}</ul> : <p className="empty-copy">No reminders scheduled.</p>}</section>
      <section className="application-panel document-panel"><h2>Document coordination</h2><p className="muted-copy">Document status records your evidence only. It does not confirm official acceptance. Uploading and analysis now live in the separate private Document Lab; linking a version still requires your explicit confirmation there.</p><Link className="button button-quiet" to="/document-lab">Open private Document Lab</Link><form className="inline-form" onSubmit={(event) => void perform(() => addDocument(event))}><label>Document name<input value={documentName} onChange={(event) => setDocumentName(event.target.value)} required /></label><label className="checkbox-label"><input type="checkbox" checked={documentRequired} onChange={(event) => setDocumentRequired(event.target.checked)} /> Required</label><button className="button button-primary" type="submit">Add document</button></form><div className="document-list">{application.documents.map((document) => <form className="document-card" key={document.id} onSubmit={(event) => void perform(() => saveDocument(document.id, event))}><label>Name<input name="name" defaultValue={document.name} required /></label><label>File name<input name="file_name" defaultValue={document.file_name ?? ""} /></label><label>Content type<input name="content_type" defaultValue={document.content_type ?? ""} placeholder="application/pdf" /></label><label>Size (bytes)<input name="size_bytes" type="number" min="0" defaultValue={document.size_bytes ?? ""} /></label><label>Version<input name="version_label" defaultValue={document.version_label ?? ""} /></label><label>Review date<input name="reviewed_at" type="datetime-local" defaultValue={localDateTime(document.reviewed_at)} /></label><label>Expiry date<input name="expires_at" type="datetime-local" defaultValue={localDateTime(document.expires_at)} /></label><label className="checkbox-label"><input name="is_required" type="checkbox" defaultChecked={document.is_required} /> Required</label><label className="checkbox-label"><input name="is_complete" type="checkbox" defaultChecked={document.is_complete} /> Evidence complete</label><button className="button button-quiet" type="submit">Save metadata</button></form>)}</div>{!application.documents.length ? <p className="empty-copy">No documents are being coordinated yet.</p> : null}</section>
      <section className="application-panel"><h2>Private notes</h2><textarea rows={7} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Keep your personal next steps here." /><div className="card-actions"><button className="button button-primary" type="button" onClick={() => void perform(saveNotes)}>Save notes</button></div></section>
      <section className="application-panel"><h2>Activity history</h2>{events.length ? <ol className="activity-list">{events.map((event) => <li key={event.id}><strong>{humanize(event.event_type.replaceAll(".", "_"))}</strong><small>{formatDate(event.created_at)}</small></li>)}</ol> : <p className="empty-copy">No activity has been recorded yet.</p>}</section>
    </div>
  </main>;
}
