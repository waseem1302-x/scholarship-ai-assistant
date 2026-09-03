import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import { createApplication } from "../workspace/workspace";
import {
  formatDate,
  getCountryFlag,
  getDeadlineUrgency,
  getOpportunity,
  isNotFound,
  readableValue,
} from "./catalogue";
import type {
  DecisionSummaryBlock,
  OpportunityDetail,
  PublicFactScope,
  PublicScholarshipProjection,
} from "./types";

const UNKNOWN_LABEL = "Not confirmed in reviewed sources";

function Value({ children }: { children: string | number | null | undefined }) {
  return <span>{children === null || children === undefined || children === "" ? UNKNOWN_LABEL : children}</span>;
}

function summaryStateLabel(block: DecisionSummaryBlock): string {
  if (block.state === "unknown") return UNKNOWN_LABEL;
  return readableValue(block.state);
}

function formatAmount(
  amount: number | string | null,
  currency: string | null,
  frequency: string | null,
): string | null {
  if (amount === null || !currency) return null;
  const suffix = frequency ? ` / ${readableValue(frequency)}` : "";
  const displayAmount = typeof amount === "number" ? amount.toLocaleString() : amount;
  return `${currency.toUpperCase()} ${displayAmount}${suffix}`;
}

function scopeLabel(scope: PublicFactScope, projection: PublicScholarshipProjection): string | null {
  const labels: string[] = [];
  if (scope.track_id) {
    const track = projection.tracks.find((item) => item.id === scope.track_id);
    labels.push(track?.name ?? UNKNOWN_LABEL);
  }
  const scholarshipProgrammeId = scope.scholarship_programme_id ?? scope.programme_id;
  if (scholarshipProgrammeId) {
    const programme = projection.programmes.find((item) => item.id === scholarshipProgrammeId);
    labels.push(programme?.name ?? UNKNOWN_LABEL);
  }
  if (scope.institution_id) labels.push("Specific institution");
  return labels.length ? labels.join(" · ") : null;
}

function MatchAuditSection() {
  const { user } = useAuth();

  if (!user) {
    return (
      <section className="detail-match-banner match-guest-banner" aria-label="Sign in to view match score">
        <div className="match-guest-content">
          <div className="match-guest-icon">✨</div>
          <div>
            <p className="match-guest-title">Sign in to check your profile match score</p>
            <p className="match-guest-subtitle">
              Build your profile, then review your scholarship matches in one place.
            </p>
          </div>
        </div>
        <Link className="button button-quiet match-guest-btn" to="/auth">
          Sign in to view match ➔
        </Link>
      </section>
    );
  }

  return (
    <section className="detail-match-banner match-guest-banner" aria-label="Open profile matches">
      <div className="match-guest-content">
        <div className="match-guest-icon">✨</div>
        <div>
          <p className="match-guest-title">Review this scholarship in your matches</p>
          <p className="match-guest-subtitle">
            Open your matches to compare your saved profile with available scholarship criteria.
          </p>
        </div>
      </div>
      <Link className="button button-quiet match-guest-btn" to="/matches">
        Open your matches ➔
      </Link>
    </section>
  );
}

function SaveToTrackerButton({ opportunityId }: { opportunityId: string }) {
  const { user } = useAuth();
  const [isSaving, setIsSaving] = useState(false);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (!user) {
    return (
      <div className="save-to-tracker">
        <Link className="button button-primary hero-btn-save" to="/auth">
          <span>🚀</span> Save & track in application plan
        </Link>
      </div>
    );
  }

  if (user.role !== "student") return null;

  async function save() {
    setIsSaving(true);
    setMessage(null);
    try {
      const application = await createApplication(opportunityId);
      setApplicationId(application.id);
      setMessage("Saved. Your application plan is ready.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save this opportunity.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="save-to-tracker">
      <button
        className="button button-primary hero-btn-save"
        type="button"
        onClick={save}
        disabled={isSaving || Boolean(applicationId)}
      >
        <span>🚀</span> {isSaving ? "Saving..." : applicationId ? "Saved to Tracker" : "Save & track"}
      </button>
      {message ? (
        <p className={message.startsWith("Saved.") ? "form-success" : "form-error"} role="status">
          {message}
        </p>
      ) : null}
      {applicationId ? (
        <Link className="button button-quiet open-plan-link" to={`/applications/${applicationId}`}>
          Open application plan ➔
        </Link>
      ) : null}
    </div>
  );
}

export function OpportunityDetailPage() {
  const { opportunityId } = useParams();

  const { data: opportunity, error, isLoading, reload } = useServerQuery<OpportunityDetail>(
    opportunityId ?? "missing-opportunity",
    (signal) => getOpportunity(opportunityId!, signal),
    Boolean(opportunityId),
  );

  if (isLoading) {
    return (
      <main className="detail-page page-width" aria-live="polite" aria-busy="true">
        <Link className="back-link" to="/catalogue">← Back to scholarships</Link>
        <div className="detail-shimmer-container">
          <div className="skeleton-line skeleton-title"></div>
          <div className="skeleton-line skeleton-subtitle"></div>
          <div className="skeleton-card-large"></div>
        </div>
      </main>
    );
  }

  if (error || !opportunity) {
    return (
      <main className="detail-page page-width" aria-live="polite">
        <Link className="back-link" to="/catalogue">← Back to scholarships</Link>
        <div className="catalogue-message error-message" role="alert">
          <h1>{isNotFound(error) ? "This opportunity is no longer publicly available." : "We could not load this opportunity."}</h1>
          <p>{isNotFound(error) ? "It may have closed or returned to review after its source changed." : error instanceof Error ? error.message : "Please try again."}</p>
          <Link className="button button-primary" to="/catalogue">Return to scholarships</Link>
          {!isNotFound(error) ? <button className="button button-quiet" type="button" onClick={reload}>Try again</button> : null}
        </div>
      </main>
    );
  }

  const projection = opportunity.projection;
  const reviewedDeadline = projection.deadlines.find(
    (deadline) => deadline.deadline_at || deadline.deadline_text || deadline.local_date,
  );
  const deadlineDate = reviewedDeadline?.deadline_at ?? reviewedDeadline?.local_date ?? null;
  const urgency = deadlineDate ? getDeadlineUrgency(deadlineDate) : null;
  const countryFlag = getCountryFlag(opportunity.country);
  const degrees = Array.from(
    new Set(projection.programmes.flatMap((programme) => programme.degree_levels)),
  );
  const officialAppUrl =
    projection.tracks.find((track) => track.application_url)?.application_url ??
    projection.steps.find((step) => step.application_url)?.application_url ??
    projection.resources.find(
      (resource) => resource.resource_type === "application_portal" && resource.url,
    )?.url ??
    null;
  const applicationMethod = projection.tracks.find(
    (track) => track.application_method,
  )?.application_method;
  const applicationFee = projection.funding.find((item) =>
    item.component_type?.toLowerCase().includes("application_fee"),
  );
  const applicationFeeText = applicationFee
    ? formatAmount(applicationFee.amount, applicationFee.currency, applicationFee.frequency) ??
      applicationFee.description ??
      applicationFee.original_text ??
      (applicationFee.coverage_status ? readableValue(applicationFee.coverage_status) : null)
    : null;
  const cycleLabel = projection.cycle?.intake_year
    ? `${projection.cycle.intake_year} Academic Cycle`
    : projection.cycle?.label ?? UNKNOWN_LABEL;
  const summary = projection.summary;
  const summaryBlocks: Array<[string, DecisionSummaryBlock]> = summary
    ? [
        ["Overview", summary.overview],
        ["Funding", summary.funding],
        ["Eligibility", summary.eligibility],
        ["Application route", summary.application_route],
      ]
    : [];

  return (
    <main className="detail-page page-width" aria-live="polite">
      
      {/* Top Breadcrumb */}
      <div className="detail-top-nav">
        <Link className="back-link" to="/catalogue">← Back to scholarships</Link>
        <span className="detail-freshness-pill">
          ✓ Reviewed official source
        </span>
      </div>

      {/* Hero Header Card */}
      <section className="detail-hero-luxury" aria-label="Scholarship Overview">
        <div className="detail-hero-pills">
          <span className="pill-verified">✓ Reviewed record</span>
          <span className="pill-country">{countryFlag} {opportunity.country}</span>
          {degrees.map((deg) => (
            <span key={deg} className="pill-degree">🎓 {readableValue(deg)}</span>
          ))}
          <span className="pill-funding">
            💰 {summary?.funding.state === "confirmed" ? "Funding reviewed" : UNKNOWN_LABEL}
          </span>
          <span className={`urgency-pill urgency-${urgency?.tier ?? "unknown"}`}>
            {urgency?.icon ?? "🗓️"} {urgency?.label ?? reviewedDeadline?.deadline_text ?? UNKNOWN_LABEL}
          </span>
        </div>

        <div className="detail-hero-titles">
          <h1 className="detail-hero-h1">{opportunity.name}</h1>
          <p className="detail-hero-subtitle">
            {opportunity.provider_name}
            {opportunity.university_name ? ` · ${opportunity.university_name}` : ""}
          </p>
        </div>

        <div className="detail-hero-action-bar">
          <SaveToTrackerButton opportunityId={opportunity.id} />
          {officialAppUrl ? (
            <a
              className="button hero-btn-portal"
              href={officialAppUrl}
              target="_blank"
              rel="noreferrer"
            >
              <span>↗</span> Open official application portal
            </a>
          ) : null}
        </div>

        <div className="detail-hero-footer-meta">
          <span>Intake: <strong>{cycleLabel}</strong></span>
          <span>•</span>
          <span>
            Last verified:{" "}
            <strong>
              <Value>
                {opportunity.last_verified_at || opportunity.source.last_verified_at
                  ? formatDate(opportunity.last_verified_at || opportunity.source.last_verified_at)
                  : null}
              </Value>
            </strong>
          </span>
        </div>
      </section>

      {/* Two-Column Dossier Layout */}
      <div className="detail-layout-grid">
        
        {/* Left Column: Dossier Details */}
        <div className="detail-main-column">

          <section className="detail-card-section" aria-label="Reviewed decision summary">
            <div className="section-header-row">
              <div>
                <h2 className="section-heading">Decision summary</h2>
                <p className="section-subtext">Only claims linked to reviewed official evidence</p>
              </div>
            </div>
            {summaryBlocks.length ? (
              <div className="funding-matrix-grid">
                {summaryBlocks.map(([label, block], index) => (
                  <article
                    className={`funding-card-accent ${index % 2 ? "accent-blue" : "accent-teal"}`}
                    key={label}
                  >
                    <div className="funding-card-top">
                      <span className="funding-card-label">{label}</span>
                      <span className="funding-status-pill">{summaryStateLabel(block)}</span>
                    </div>
                    <p className="funding-card-desc">
                      {block.state === "unknown" ? UNKNOWN_LABEL : block.text}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          <section className="detail-card-section" aria-label="Financial Coverage Package">
            <div className="section-header-row">
              <div>
                <h2 className="section-heading">Funding</h2>
                <p className="section-subtext">Components confirmed by reviewed source evidence</p>
              </div>
              {summary ? (
                <span className="section-badge-green">{summaryStateLabel(summary.funding)}</span>
              ) : null}
            </div>
            {projection.funding.length ? (
              <div className="funding-matrix-grid">
                {projection.funding.map((item, index) => {
                  const scope = scopeLabel(item.scope, projection);
                  const amount = formatAmount(item.amount, item.currency, item.frequency);
                  return (
                    <article
                      className={`funding-card-accent ${index % 2 ? "accent-blue" : "accent-teal"}`}
                      key={item.id}
                    >
                      <div className="funding-card-top">
                        <span className="funding-card-label">
                          {item.component_type ? readableValue(item.component_type) : "Funding component"}
                        </span>
                        <span className="funding-status-pill">
                          {item.coverage_status ? readableValue(item.coverage_status) : UNKNOWN_LABEL}
                        </span>
                      </div>
                      {amount ? <h3 className="funding-card-value">{amount}</h3> : null}
                      <p className="funding-card-desc">
                        {item.description ?? item.original_text ?? item.qualifier ?? UNKNOWN_LABEL}
                      </p>
                      {scope ? <p className="section-subtext">Applies to: {scope}</p> : null}
                    </article>
                  );
                })}
              </div>
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          <section className="detail-card-section" aria-label="Eligibility Criteria">
            <div className="section-header-row">
              <div>
                <h2 className="section-heading">Eligibility</h2>
                <p className="section-subtext">Reviewed rules with their original scope preserved</p>
              </div>
            </div>
            {projection.eligibility.length ? (
              <dl className="eligibility-dl">
                {projection.eligibility.map((rule) => {
                  const scope = scopeLabel(rule.scope, projection);
                  return (
                    <div className="eligibility-row" key={rule.id}>
                      <dt>{rule.rule_type ? readableValue(rule.rule_type) : "Eligibility rule"}</dt>
                      <dd>
                        {rule.original_text ?? rule.condition ?? UNKNOWN_LABEL}
                        {scope ? <small> · Applies to: {scope}</small> : null}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          <section className="detail-card-section" aria-label="Application Routes">
            <h2 className="section-heading">Application routes</h2>
            {projection.tracks.length ? (
              <dl className="eligibility-dl">
                {projection.tracks.map((track) => (
                  <div className="eligibility-row" key={track.id}>
                    <dt>{track.name ?? UNKNOWN_LABEL}</dt>
                    <dd>
                      {track.application_method ?? UNKNOWN_LABEL}
                      {track.application_url ? (
                        <> · <a href={track.application_url} target="_blank" rel="noreferrer">Open route ↗</a></>
                      ) : null}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          <section className="detail-card-section" aria-label="Reviewed Deadlines">
            <h2 className="section-heading">Deadlines</h2>
            {projection.deadlines.length ? (
              <dl className="eligibility-dl">
                {projection.deadlines.map((deadline) => {
                  const scope = scopeLabel(deadline.scope, projection);
                  return (
                    <div className="eligibility-row" key={deadline.id}>
                      <dt>{deadline.label ?? (deadline.deadline_type ? readableValue(deadline.deadline_type) : "Deadline")}</dt>
                      <dd>
                        {deadline.deadline_at || deadline.local_date
                          ? formatDate(deadline.deadline_at ?? deadline.local_date)
                          : deadline.deadline_text ?? UNKNOWN_LABEL}
                        {scope ? <small> · Applies to: {scope}</small> : null}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          <section className="detail-card-section" aria-label="Required Application Documents">
            <h2 className="section-heading">Required documents</h2>
            {projection.documents.length ? (
              <div className="documents-checklist-grid">
                {projection.documents.map((document) => (
                  <div key={document.id} className="document-check-card">
                    <span className="doc-check-icon">
                      {document.required === true ? "✓" : document.required === false ? "○" : "?"}
                    </span>
                    <span className="doc-check-title">
                      {document.name ?? UNKNOWN_LABEL}
                      {document.required === null ? ` · ${UNKNOWN_LABEL}` : document.required ? " · Required" : " · Optional"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          <section className="detail-card-section" aria-label="Application Steps">
            <h2 className="section-heading">Application steps</h2>
            {projection.steps.length ? (
              <ol className="warning-list">
                {projection.steps.map((step) => (
                  <li key={step.id}>
                    <strong>{step.title ?? UNKNOWN_LABEL}</strong>
                    {step.description || step.original_text || step.outcome ? (
                      <> — {step.description ?? step.original_text ?? step.outcome}</>
                    ) : null}
                    {scopeLabel(step.scope, projection) ? (
                      <small> · Applies to: {scopeLabel(step.scope, projection)}</small>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          {projection.known_unknowns.length ? (
            <section className="detail-warning-luxury" aria-label="Information not yet confirmed">
              <h3 className="warning-heading">Information not yet confirmed</h3>
              <ul className="warning-list">
                {projection.known_unknowns.map((dimension) => (
                  <li key={dimension}>{readableValue(dimension)}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="evidence-vault-navy" aria-label="Reviewed source citations">
            <div className="evidence-vault-top">
              <div className="evidence-vault-brand">
                <span className="vault-lock-icon">🔒</span>
                <span className="vault-label">REVIEWED SOURCE CITATIONS</span>
              </div>
            </div>
            {projection.evidence.length ? (
              projection.evidence.map((evidence) => (
                <article key={evidence.id}>
                  <blockquote className="evidence-quote">“{evidence.excerpt}”</blockquote>
                  <div className="evidence-vault-footer">
                    <span>
                      {evidence.source_title} · Reviewed{" "}
                      {evidence.last_verified_at ? formatDate(evidence.last_verified_at) : UNKNOWN_LABEL}
                    </span>
                    <a className="evidence-source-btn" href={evidence.source_url} target="_blank" rel="noreferrer">
                      Open cited source ↗
                    </a>
                  </div>
                </article>
              ))
            ) : (
              <p>{UNKNOWN_LABEL}</p>
            )}
          </section>

          <MatchAuditSection />

          {/* End-of-Dossier Finale Card */}
          <section className="dossier-finale-card">
            <div className="dossier-finale-text">
              <h3>Ready to apply for {opportunity.name}?</h3>
              <p>Save this to your workspace to track application tasks and reviewed deadlines.</p>
            </div>
            <div className="dossier-finale-actions">
              <SaveToTrackerButton opportunityId={opportunity.id} />
              {officialAppUrl ? (
                <a className="button hero-btn-portal" href={officialAppUrl} target="_blank" rel="noreferrer">
                  <span>↗</span> Official portal
                </a>
              ) : null}
            </div>
          </section>

        </div>

        {/* Right Column: Sticky Action Sidebar */}
        <aside className="detail-sidebar-column">
          <div className="detail-sticky-card">
            
            <div className="sidebar-deadline-box">
              <span className="sidebar-eyebrow">Application Window</span>
              <div className="sidebar-urgency-row">
                <span className="sidebar-urgency-title">
                  {urgency?.icon ?? "🗓️"} {urgency?.label ?? reviewedDeadline?.deadline_text ?? UNKNOWN_LABEL}
                </span>
                <span className="sidebar-status-tag">
                  {reviewedDeadline ? "Reviewed" : UNKNOWN_LABEL}
                </span>
              </div>
              <p className="sidebar-date-text">
                Deadline: <strong>{deadlineDate ? formatDate(deadlineDate) : reviewedDeadline?.deadline_text ?? UNKNOWN_LABEL}</strong>
              </p>
              <p className="sidebar-date-text">
                Intake: <strong>{cycleLabel}</strong>
              </p>
            </div>

            <hr className="sidebar-divider" />

            <div className="sidebar-action-stack">
              <SaveToTrackerButton opportunityId={opportunity.id} />
              {officialAppUrl ? (
                <a
                  className="button hero-btn-portal sidebar-portal-btn"
                  href={officialAppUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span>↗</span> Open official portal
                </a>
              ) : null}
            </div>

            <hr className="sidebar-divider" />

            <div className="sidebar-meta-list">
              <div className="sidebar-meta-row">
                <span>Application Fee:</span>
                <strong className="text-teal"><Value>{applicationFeeText}</Value></strong>
              </div>
              <div className="sidebar-meta-row">
                <span>Method:</span>
                <strong><Value>{applicationMethod}</Value></strong>
              </div>
            </div>

          </div>

          <p className="sidebar-legal-caption">
            🔒 Information compiled from official verified publications. Always confirm final requirements directly on the provider portal.
          </p>
        </aside>

      </div>

    </main>
  );
}
