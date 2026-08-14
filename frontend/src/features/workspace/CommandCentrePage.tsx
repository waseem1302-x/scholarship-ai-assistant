import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { formatDate } from "../catalogue/catalogue";
import type { Application, CommandCentre } from "./types";
import {
  deleteApplicationData,
  exportApplicationData,
  getApplications,
  getCommandCentre,
  getNotificationPreference,
  humanize,
  updateApplication,
  updateNotificationPreference,
  updateApplicationTask,
} from "./workspace";

function ApplicationCard({ application, onChanged }: { application: Application; onChanged: () => void }) {
  const [saving, setSaving] = useState(false);
  async function complete(taskId: string) {
    setSaving(true);
    try { await updateApplicationTask(application.id, taskId, { status: "completed", completion_evidence: "Marked complete by student" }); onChanged(); }
    finally { setSaving(false); }
  }
  async function startPreparing() {
    setSaving(true);
    try { await updateApplication(application.id, { lifecycle: "preparing", expected_version: application.version }); onChanged(); }
    finally { setSaving(false); }
  }
  const openTasks = application.tasks.filter((task) => task.status !== "completed" && task.status !== "dismissed");
  return <article className="command-card"><div className="command-card-head"><div><p className="eyebrow">{humanize(application.lifecycle)}</p><h2>{application.opportunity.name}</h2><p>{application.opportunity.provider_name} · Official deadline {formatDate(application.official_deadline)} ({application.official_deadline_timezone})</p></div><Link className="detail-link" to={`/applications/${application.id}`}>Open workspace</Link></div>
    {application.deadline_urgency !== "upcoming" ? <p className="deadline-alert">Official deadline is {humanize(application.deadline_urgency)}. Confirm it using the linked official evidence.</p> : null}
    <div className="task-board"><h3>Next actions</h3>{openTasks.slice(0, 4).map((task) => <div className="command-task" key={task.id}><span>{task.title}</span><small>{humanize(task.category)} · {task.due_at ? formatDate(task.due_at) : "No task deadline"}</small><button className="button button-quiet" type="button" disabled={saving} onClick={() => void complete(task.id)}>Complete</button></div>)}{!openTasks.length ? <p className="empty-copy">No open tasks yet.</p> : null}</div>
    <div className="card-actions">{application.lifecycle === "saved" ? <button className="button button-primary" type="button" onClick={() => void startPreparing()} disabled={saving}>Start preparing</button> : null}<span className="muted-copy">{application.tasks.filter((task) => task.status === "completed").length} tasks marked complete by you</span></div>
  </article>;
}

export function DashboardSections({ centre }: { centre: CommandCentre }) {
  const sections = [
    ["Urgent actions", centre.urgent_tasks.map((task) => task.title)],
    ["Blocked tasks", centre.blocked_tasks.map((task) => task.title)],
    ["Blocked applications", centre.blocked_applications.map((item) => item.opportunity.name)],
    ["Approaching deadlines", centre.approaching_deadlines.map((item) => item.opportunity.name)],
    ["Recently changed opportunities", centre.recently_changed_opportunities.map((item) => item.opportunity.name)],
    ["Submitted applications", centre.submitted_applications.map((item) => item.opportunity.name)],
    ["Upcoming reminders", centre.upcoming_reminders.map((item) => item.message || formatDate(item.scheduled_at))],
  ] as const;
  return <section className="dashboard-sections" aria-label="Command centre overview">{sections.map(([heading, items]) => <article key={heading}><h2>{heading}</h2>{items.length ? <ul>{items.slice(0, 4).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p>No items right now.</p>}</article>)}</section>;
}

export function CommandCentrePage() {
  const { user, isRestoring } = useAuth();
  const [applications, setApplications] = useState<Application[]>([]);
  const [centre, setCentre] = useState<CommandCentre | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [remindersEnabled, setRemindersEnabled] = useState(true);
  const load = (signal?: AbortSignal) => { setLoading(true); setError(null); void Promise.all([getApplications(signal), getCommandCentre(signal), getNotificationPreference(signal)]).then(([items, dashboard, preferences]) => { setApplications(items); setCentre(dashboard); setRemindersEnabled(preferences.in_app_enabled); }).catch((reason: unknown) => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Unable to load your application workspace."); }).finally(() => { if (!signal?.aborted) setLoading(false); }); };
  useEffect(() => { const controller = new AbortController(); if (user?.role === "student") load(controller.signal); return () => controller.abort(); }, [user]);
  async function exportData() { const exported = await exportApplicationData(); const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = "scholarship-application-data.json"; link.click(); URL.revokeObjectURL(url); }
  async function deleteData() { if (!window.confirm("Delete all of your application workspaces and saved tracker data? This cannot be undone.")) return; await deleteApplicationData(); load(); }
  async function toggleReminders() { const preference = await updateNotificationPreference(!remindersEnabled); setRemindersEnabled(preference.in_app_enabled); if (!preference.in_app_enabled) load(); }
  if (isRestoring) return <main className="page-width loading-page">Restoring your secure session…</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "student") return <Navigate replace to="/dashboard" />;
  return <main className="workspace-tool page-width" aria-busy={loading}><section className="tool-header"><div><p className="eyebrow">Application command centre</p><h1>Know what needs your attention.</h1><p className="lead">Tasks, deadlines, reminders, and your own completion evidence stay private to your account.</p></div><div className="command-tools"><Link className="button button-quiet" to="/catalogue">Add verified opportunity</Link><button className="button button-quiet" type="button" onClick={() => void exportData()}>Export data</button><button className="button button-quiet" type="button" onClick={() => void toggleReminders()}>{remindersEnabled ? "Pause in-app reminders" : "Enable in-app reminders"}</button><button className="button button-danger" type="button" onClick={() => void deleteData()}>Delete data</button></div></section>
    {loading ? <div className="catalogue-message">Loading your command centre…</div> : null}{error ? <div className="catalogue-message error-message" role="alert"><p>{error}</p><button className="button button-quiet" onClick={() => load()}>Try again</button></div> : null}
    {!loading && !error && centre ? <><section className="command-summary" aria-label="Application status"><div><strong>{centre.urgent_tasks.length}</strong><span>urgent actions</span></div><div><strong>{centre.blocked_applications.length}</strong><span>blocked applications</span></div><div><strong>{centre.upcoming_reminders.length}</strong><span>upcoming reminders</span></div></section><DashboardSections centre={centre} /></> : null}
    {!loading && !error && !applications.length ? <div className="catalogue-message"><h2>No applications yet.</h2><p>Open a verified opportunity and create an application workspace to track the work without losing source context.</p><Link className="button button-primary" to="/catalogue">Browse opportunities</Link></div> : null}<section className="command-list">{applications.map((application) => <ApplicationCard key={application.id} application={application} onChanged={load} />)}</section>
  </main>;
}
