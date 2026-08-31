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
  updateApplicationTask,
  updateNotificationPreference,
} from "./workspace";

function ApplicationCard({ application, onChanged }: { application: Application; onChanged: () => void }) {
  const [saving, setSaving] = useState(false);

  async function complete(taskId: string) {
    setSaving(true);
    try {
      await updateApplicationTask(application.id, taskId, {
        status: "completed",
        completion_evidence: "Marked complete by student",
      });
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  async function startPreparing() {
    setSaving(true);
    try {
      await updateApplication(application.id, {
        lifecycle: "preparing",
        expected_version: application.version,
      });
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  const openTasks = application.tasks.filter(
    (task) => task.status !== "completed" && task.status !== "dismissed",
  );
  const completedTasks = application.tasks.filter((task) => task.status === "completed");
  const totalTasks = application.tasks.length;
  const progressPercent = totalTasks > 0 ? Math.round((completedTasks.length / totalTasks) * 100) : 0;

  return (
    <article className={`luxury-card command-app-card command-app-${application.lifecycle}`}>
      {/* Top Header Row */}
      <div className="command-app-header">
        <div className="command-app-title-group">
          <div className="command-app-meta-pills">
            <span className={`stage-pill stage-${application.lifecycle}`}>
              <span className="stage-dot" /> {humanize(application.lifecycle)}
            </span>
            {application.deadline_urgency !== "upcoming" ? (
              <span className="deadline-urgency-badge">
                ⚠️ Deadline {humanize(application.deadline_urgency)}
              </span>
            ) : null}
          </div>
          <h2 className="command-app-heading">{application.opportunity.name}</h2>
          <p className="command-app-provider">
            {application.opportunity.provider_name} · Official deadline {formatDate(application.official_deadline)} ({application.official_deadline_timezone})
          </p>
        </div>

        <Link className="open-workspace-btn" to={`/applications/${application.id}`}>
          Open workspace ➔
        </Link>
      </div>

      {/* Progress Bar (if tasks exist) */}
      {totalTasks > 0 ? (
        <div className="app-progress-container">
          <div className="app-progress-labels">
            <span>Workflow Progress</span>
            <span className="progress-value-text">
              {completedTasks.length} of {totalTasks} Tasks Completed ({progressPercent}%)
            </span>
          </div>
          <div className="app-progress-track">
            <div
              className="app-progress-fill"
              style={{ width: `${progressPercent}%` }}
              role="progressbar"
              aria-valuenow={progressPercent}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
        </div>
      ) : null}

      {/* Next Action Tasks Board */}
      <div className="command-task-board">
        <div className="task-board-header">
          <h3>Next Required Actions</h3>
          {openTasks.length > 4 ? (
            <span className="tasks-remaining-tag">+{openTasks.length - 4} more in workspace</span>
          ) : null}
        </div>

        {openTasks.slice(0, 4).map((task) => (
          <div className="command-task-row" key={task.id}>
            <div className="task-left-info">
              <span className="task-title-bold">{task.title}</span>
              <span className="task-meta-sub">
                {humanize(task.category)} · {task.due_at ? `Due ${formatDate(task.due_at)}` : "Flexible deadline"}
              </span>
            </div>
            <div className="task-action-buttons">
              <Link
                to={`/assistant?prompt=${encodeURIComponent(`Draft and review task: "${task.title}" for ${application.opportunity.name}`)}`}
                className="copilot-task-chip"
              >
                ✨ Copilot
              </Link>
              <button
                className="button button-quiet complete-task-btn"
                type="button"
                disabled={saving}
                onClick={() => void complete(task.id)}
              >
                Done
              </button>
            </div>
          </div>
        ))}

        {!openTasks.length ? (
          <p className="empty-tasks-copy">✓ All current stage tasks completed. Ready for next submission milestone!</p>
        ) : null}
      </div>

      {/* Card Footer Actions */}
      <div className="command-card-footer">
        {application.lifecycle === "saved" ? (
          <button
            className="button button-primary start-preparing-btn"
            type="button"
            onClick={() => void startPreparing()}
            disabled={saving}
          >
            Start preparing application
          </button>
        ) : (
          <span className="completed-counter-text">
            ✓ {completedTasks.length} tasks marked complete by you
          </span>
        )}
        <span className="muted-timestamp">Private workspace data</span>
      </div>
    </article>
  );
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

  return (
    <section className="dashboard-sections-luxury" aria-label="Command centre overview">
      {sections.map(([heading, items]) => (
        <article className="dashboard-radar-box" key={heading}>
          <div className="radar-box-header">
            <h2>{heading}</h2>
            <span className="radar-box-count">{items.length}</span>
          </div>
          {items.length ? (
            <ul className="radar-box-list">
              {items.slice(0, 4).map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="radar-box-empty">No items right now.</p>
          )}
        </article>
      ))}
    </section>
  );
}

export function CommandCentrePage() {
  const { user, isRestoring } = useAuth();
  const [applications, setApplications] = useState<Application[]>([]);
  const [centre, setCentre] = useState<CommandCentre | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [remindersEnabled, setRemindersEnabled] = useState(true);

  const load = (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    void Promise.all([getApplications(signal), getCommandCentre(signal), getNotificationPreference(signal)])
      .then(([items, dashboard, preferences]) => {
        setApplications(items);
        setCentre(dashboard);
        setRemindersEnabled(preferences.in_app_enabled);
      })
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "Unable to load your application workspace.");
        }
      })
      .finally(() => {
        if (!signal?.aborted) setLoading(false);
      });
  };

  useEffect(() => {
    const controller = new AbortController();
    if (user?.role === "student") load(controller.signal);
    return () => controller.abort();
  }, [user]);

  async function exportData() {
    const exported = await exportApplicationData();
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "scholarship-application-data.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function deleteData() {
    if (!window.confirm("Delete all of your application workspaces and saved tracker data? This cannot be undone.")) {
      return;
    }
    await deleteApplicationData();
    load();
  }

  async function toggleReminders() {
    const preference = await updateNotificationPreference(!remindersEnabled);
    setRemindersEnabled(preference.in_app_enabled);
    if (!preference.in_app_enabled) load();
  }

  if (isRestoring) return <main className="page-width loading-page">Restoring your secure session…</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "student") return <Navigate replace to="/dashboard" />;

  const activePreparing = applications.filter((a) => a.lifecycle === "preparing").length;
  const activeSaved = applications.filter((a) => a.lifecycle === "saved").length;

  return (
    <main className="command-centre-page" aria-busy={loading}>
      <div className="command-centre-shell">

        {/* Header Title & Tools Bar */}
        <section className="command-header-toolbar">
          <div className="command-header-copy">
            <span className="eyebrow-pill">🎯 Real-Time Decision System</span>
            <h1>Application Command Centre</h1>
            <p className="lead">
              Active workflows, deadline risk radar, and next actions — grounded with your personal evidence.
            </p>
          </div>

          <div className="command-tools-cluster">
            <Link className="button button-primary add-scholarship-cta" to="/catalogue">
              <span>+</span> Add Scholarship
            </Link>
            <button className="button button-quiet" type="button" onClick={() => void exportData()}>
              📥 Export Data
            </button>
            <button className="button button-quiet" type="button" onClick={() => void toggleReminders()}>
              {remindersEnabled ? "🔔 Reminders: On" : "🔕 Reminders: Paused"}
            </button>
            <button className="button button-danger" type="button" onClick={() => void deleteData()}>
              Delete Data
            </button>
          </div>
        </section>

        {loading ? (
          <div className="clean-feed-card loading-card" aria-live="polite">
            <p>Loading your command centre…</p>
          </div>
        ) : null}

        {error ? (
          <div className="catalogue-message error-message" role="alert">
            <p>{error}</p>
            <button className="button button-quiet" onClick={() => load()}>Try again</button>
          </div>
        ) : null}

        {!loading && !error && centre ? (
          <>
            {/* 1. Executive 4-KPI Metric Bar */}
            <section className="executive-kpi-bar" aria-label="Executive workspace metrics">
              <div className="metric-kpi-box border-kpi-blue">
                <div>
                  <span className="kpi-label">In Progress</span>
                  <strong className="kpi-value">{applications.length} Awards</strong>
                  <span className="kpi-subtext">{activePreparing} Preparing · {activeSaved} Saved</span>
                </div>
                <div className="kpi-icon-pill icon-blue">📁</div>
              </div>

              <div className="metric-kpi-box border-kpi-red">
                <div>
                  <span className="kpi-label">Urgent Tasks</span>
                  <strong className="kpi-value text-urgent">{centre.urgent_tasks.length} Tasks</strong>
                  <span className="kpi-subtext text-urgent">Closing in &lt; 7 days</span>
                </div>
                <div className="kpi-icon-pill icon-red">⏰</div>
              </div>

              <div className="metric-kpi-box border-kpi-teal">
                <div>
                  <span className="kpi-label">Upcoming Reminders</span>
                  <strong className="kpi-value text-teal">{centre.upcoming_reminders.length} Scheduled</strong>
                  <span className="kpi-subtext text-teal">Portal & deadline notices</span>
                </div>
                <div className="kpi-icon-pill icon-teal">✓</div>
              </div>

              <div className="metric-kpi-box border-kpi-navy">
                <div>
                  <span className="kpi-label">Catalogue Monitoring</span>
                  <strong className="kpi-value">{centre.recently_changed_opportunities.length} Updates</strong>
                  <span className="kpi-subtext">Verified source sync</span>
                </div>
                <div className="kpi-icon-pill icon-navy">🔍</div>
              </div>
            </section>

            {/* 2. 7-Group Decision Radar Overview */}
            <DashboardSections centre={centre} />
          </>
        ) : null}

        {/* 3. Empty Applications State */}
        {!loading && !error && !applications.length ? (
          <div className="clean-feed-card empty-applications-card">
            <h2>No application workspaces created yet</h2>
            <p>
              Open any verified scholarship in the catalogue and create a tracked application workspace to get deadline alerts, task milestones, and document audits.
            </p>
            <Link className="button button-primary" to="/catalogue">
              Explore Verified Scholarships ➔
            </Link>
          </div>
        ) : null}

        {/* 4. Active Applications Cards Stream */}
        {!loading && !error && applications.length > 0 ? (
          <section className="applications-workspaces-stream" aria-label="Active application workspaces">
            <div className="stream-header-row">
              <h2>Your Tracked Applications ({applications.length})</h2>
              <span className="stream-sort-label">Prioritized by deadline urgency</span>
            </div>

            <div className="applications-card-grid">
              {applications.map((application) => (
                <ApplicationCard key={application.id} application={application} onChanged={load} />
              ))}
            </div>
          </section>
        ) : null}

      </div>
    </main>
  );
}
