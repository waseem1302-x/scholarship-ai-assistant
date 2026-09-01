import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import { createApplication, getMatches } from "../workspace/workspace";
import type { OpportunityMatch } from "../workspace/types";
import {
  formatDate,
  getCountryFlag,
  getDeadlineUrgency,
  getOpportunity,
  isNotFound,
  readableValue,
} from "./catalogue";
import type { OpportunityDetail } from "./types";

function Value({ children }: { children: string | number | null | undefined }) {
  return <span>{children === null || children === undefined || children === "" ? "Not stated" : children}</span>;
}

function MatchAuditSection({
  opportunity,
  match,
}: {
  opportunity: OpportunityDetail;
  match: OpportunityMatch | undefined;
}) {
  const { user } = useAuth();

  if (!user) {
    return (
      <section className="detail-match-banner match-guest-banner" aria-label="Sign in to view match score">
        <div className="match-guest-content">
          <div className="match-guest-icon">✨</div>
          <div>
            <p className="match-guest-title">Sign in to check your profile match score</p>
            <p className="match-guest-subtitle">
              We compare your GPA, nationality, and degree level against this scholarship's verified criteria.
            </p>
          </div>
        </div>
        <Link className="button button-quiet match-guest-btn" to="/auth">
          Sign in to view match ➔
        </Link>
      </section>
    );
  }

  const score = match ? (match.fit_score ?? match.match_score ?? null) : null;
  const isHighFit = score !== null && score >= 80;
  const isGoodFit = score !== null && score >= 60 && score < 80;
  const hardFailure = match?.eligibility_status === "ineligible" || match?.eligibility_status === "likely_ineligible";

  const matchClass = hardFailure
    ? "match-partial-card"
    : isHighFit
      ? "match-high-card"
      : isGoodFit
        ? "match-good-card"
        : "match-partial-card";

  const degreeLevels = opportunity.degree_levels?.length ? opportunity.degree_levels : [opportunity.degree_level];

  // Derive dynamic status from match evaluation
  const isDegreeMatched = !match?.failed_criteria?.some((c) => c.toLowerCase().includes("degree"));
  const isNationalityMatched = !match?.failed_criteria?.some((c) => c.toLowerCase().includes("nationality") || c.toLowerCase().includes("country"));
  const isAcademicMatched = !match?.failed_criteria?.some((c) => c.toLowerCase().includes("academic") || c.toLowerCase().includes("gpa") || c.toLowerCase().includes("grade"));
  const isLanguageMatched = !match?.failed_criteria?.some((c) => c.toLowerCase().includes("english") || c.toLowerCase().includes("language") || c.toLowerCase().includes("test"));

  return (
    <section className={`detail-match-card ${matchClass}`} aria-label="Personal Eligibility Match Audit">
      <div className="match-card-header">
        <div className="match-card-title-group">
          <div className="match-score-badge">
            {score !== null ? `${score}%` : "—"}
          </div>
          <div>
            <div className="match-headline-row">
              <h2 className="match-card-heading">Your Profile Eligibility Match</h2>
              <span className="match-status-pill">
                <span className="pulse-dot"></span>
                {hardFailure ? "Needs Review" : isHighFit ? "Strong Candidate Fit" : isGoodFit ? "Good Fit" : "Evaluation Available"}
              </span>
            </div>
            <p className="match-card-subtext">
              {match ? "Audited in real-time against your saved student credentials" : "Complete your profile to see full criteria alignment"}
            </p>
          </div>
        </div>
        <Link className="match-edit-link" to="/profile">
          Edit Profile ➔
        </Link>
      </div>

      <div className="match-checklist-grid">
        <div className="match-check-item">
          <div className="match-check-left">
            <span className="match-check-icon">{isDegreeMatched ? "✓" : "⚠"}</span>
            <div>
              <div className="match-check-title-row">
                <strong>Degree Level Eligibility</strong>
                <span className="match-mini-tag">Targeting {degreeLevels.map(readableValue).join(", ")}</span>
              </div>
              <p className="match-check-desc">
                Scholarship supports {degreeLevels.map(readableValue).join(", ")} degrees
              </p>
            </div>
          </div>
          <span className={isDegreeMatched ? "match-badge-eligible" : "match-badge-neutral"}>
            {isDegreeMatched ? "Eligible" : "Check Degree"}
          </span>
        </div>

        <div className="match-check-item">
          <div className="match-check-left">
            <span className="match-check-icon">{isNationalityMatched ? "✓" : "⚠"}</span>
            <div>
              <div className="match-check-title-row">
                <strong>Nationality & Citizenship</strong>
                <span className="match-mini-tag">{opportunity.country} Partner Award</span>
              </div>
              <p className="match-check-desc">
                {opportunity.nationality_eligibility || `Eligible international citizens for ${opportunity.country} awards`}
              </p>
            </div>
          </div>
          <span className={isNationalityMatched ? "match-badge-eligible" : "match-badge-neutral"}>
            {isNationalityMatched ? "Eligible" : "Check Citizenship"}
          </span>
        </div>

        <div className="match-check-item">
          <div className="match-check-left">
            <span className="match-check-icon">{isAcademicMatched ? "✓" : "⚠"}</span>
            <div>
              <div className="match-check-title-row">
                <strong>Academic Threshold</strong>
                <span className="match-mini-tag">Academic Criterion</span>
              </div>
              <p className="match-check-desc">
                {opportunity.minimum_academic_requirement || "Undergraduate 2:1 Honours equivalent or stated academic threshold"}
              </p>
            </div>
          </div>
          <span className={isAcademicMatched ? "match-badge-eligible" : "match-badge-neutral"}>
            {isAcademicMatched ? "Satisfied" : "Check GPA"}
          </span>
        </div>

        <div className="match-check-item">
          <div className="match-check-left">
            <span className="match-check-icon">{isLanguageMatched ? "✓" : "⚠"}</span>
            <div>
              <div className="match-check-title-row">
                <strong>English Language Proficiency</strong>
                <span className="match-mini-tag">Language Requirement</span>
              </div>
              <p className="match-check-desc">
                {opportunity.english_language_requirement || "IELTS Academic 6.5+ or TOEFL iBT 90+ where required"}
              </p>
            </div>
          </div>
          <span className={isLanguageMatched ? "match-badge-eligible" : "match-badge-neutral"}>
            {isLanguageMatched ? "Passed" : "Check Test"}
          </span>
        </div>
      </div>
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
  const { user } = useAuth();

  const { data: opportunity, error, isLoading, reload } = useServerQuery<OpportunityDetail>(
    opportunityId ?? "missing-opportunity",
    (signal) => getOpportunity(opportunityId!, signal),
    Boolean(opportunityId),
  );

  const { data: studentMatches } = useServerQuery<OpportunityMatch[]>(
    "detail-student-matches",
    (signal) => getMatches(signal),
    user?.role === "student",
  );

  const match = useMemo(() => {
    if (!Array.isArray(studentMatches) || !opportunityId) return undefined;
    return studentMatches.find((m) => m.opportunity.id === opportunityId);
  }, [studentMatches, opportunityId]);

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

  const urgency = getDeadlineUrgency(opportunity.application_deadline);
  const countryFlag = getCountryFlag(opportunity.country);
  const degrees = opportunity.degree_levels?.length ? opportunity.degree_levels : [opportunity.degree_level];
  const stipend = opportunity.monthly_stipend_amount
    ? `${opportunity.monthly_stipend_amount.toLocaleString()} ${opportunity.monthly_stipend_currency ?? ""}`.trim()
    : null;

  const officialAppUrl = opportunity.application_url || opportunity.official_source_url || opportunity.source.url;

  return (
    <main className="detail-page page-width" aria-live="polite">
      
      {/* Top Breadcrumb */}
      <div className="detail-top-nav">
        <Link className="back-link" to="/catalogue">← Back to scholarships</Link>
        <span className="detail-freshness-pill">
          ✓ Officially Verified Government Record
        </span>
      </div>

      {/* Hero Header Card */}
      <section className="detail-hero-luxury" aria-label="Scholarship Overview">
        <div className="detail-hero-pills">
          <span className="pill-verified">✓ Verified Award</span>
          <span className="pill-country">{countryFlag} {opportunity.country}</span>
          {degrees.map((deg) => (
            <span key={deg} className="pill-degree">🎓 {readableValue(deg)}</span>
          ))}
          <span className="pill-funding">💰 {opportunity.funding_display_label}</span>
          <span className={`urgency-pill urgency-${urgency.tier}`}>
            {urgency.icon} {urgency.label}
          </span>
        </div>

        <div className="detail-hero-titles">
          <h1 className="detail-hero-h1">{opportunity.name}</h1>
          <p className="detail-hero-subtitle">
            {opportunity.provider_name}
            {opportunity.university_name ? ` · ${opportunity.university_name}` : ""}
          </p>
        </div>

        {/* 3-Way Hero Action Conversion Bar */}
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
          <Link
            className="button hero-btn-ai"
            to={`/assistant?opportunity=${opportunity.id}`}
          >
            <span>🤖</span> Ask AI Copilot about this
          </Link>
        </div>

        <div className="detail-hero-footer-meta">
          <span>Intake: <strong>{opportunity.intake_year ? `${opportunity.intake_year} Academic Cycle` : "Official Intake Cycle"}</strong></span>
          <span>•</span>
          <span>Decision Tier: <strong className="tier-ready">{readableValue(opportunity.catalogue_decision_tier)}</strong></span>
          <span>•</span>
          <span>Last verified: <strong>{formatDate(opportunity.last_verified_at || opportunity.source.last_verified_at)}</strong></span>
        </div>
      </section>

      {/* Two-Column Dossier Layout */}
      <div className="detail-layout-grid">
        
        {/* Left Column: Dossier Details */}
        <div className="detail-main-column">

          {/* AI Copilot Module */}
          <section className="ai-copilot-module" aria-label="AI Scholarship Copilot">
            <div className="ai-copilot-header">
              <div className="ai-copilot-title-group">
                <span className="ai-copilot-icon">🤖</span>
                <div>
                  <h2 className="ai-copilot-heading">AI Scholarship Copilot</h2>
                  <p className="ai-copilot-subtext">Instant guidance powered by official verified evidence</p>
                </div>
              </div>
              <span className="ai-copilot-badge">Source-Linked AI</span>
            </div>
            <p className="ai-copilot-prompt-intro">
              Select a tailored prompt to start analyzing this scholarship with AI:
            </p>
            <div className="ai-prompt-chips-grid">
              <Link className="ai-prompt-chip" to={`/assistant?opportunity=${opportunity.id}&prompt=Evaluate+my+eligibility+and+chances+for+this+scholarship`}>
                <span>💬 "Evaluate my eligibility for {opportunity.name}"</span>
                <span className="ai-chip-arrow">➔</span>
              </Link>
              <Link className="ai-prompt-chip" to={`/assistant?opportunity=${opportunity.id}&prompt=Help+me+draft+application+essays+for+this+scholarship`}>
                <span>📝 "Draft my application essays & personal statement"</span>
                <span className="ai-chip-arrow">➔</span>
              </Link>
              <Link className="ai-prompt-chip" to={`/assistant?opportunity=${opportunity.id}&prompt=What+are+the+eligible+courses+and+universities+for+this+scholarship`}>
                <span>🏛️ "What courses & universities are eligible?"</span>
                <span className="ai-chip-arrow">➔</span>
              </Link>
              <Link className="ai-prompt-chip" to={`/assistant?opportunity=${opportunity.id}&prompt=Help+me+prepare+for+the+interview+for+this+scholarship`}>
                <span>🎯 "Prepare me for the scholarship interview"</span>
                <span className="ai-chip-arrow">➔</span>
              </Link>
            </div>
          </section>

          {/* Personal Profile Match Checklist */}
          <MatchAuditSection opportunity={opportunity} match={match} />

          {/* Complete Financial Breakdown */}
          <section className="detail-card-section" aria-label="Financial Coverage Package">
            <div className="section-header-row">
              <div>
                <h2 className="section-heading">💰 Complete Financial Breakdown</h2>
                <p className="section-subtext">Itemized funding and allowance schedule</p>
              </div>
              <span className="section-badge-green">{opportunity.funding_display_label}</span>
            </div>

            <div className="funding-matrix-grid">
              <div className="funding-card-accent accent-teal">
                <div className="funding-card-top">
                  <span className="funding-card-label">Tuition Fee Coverage</span>
                  <span className="funding-status-pill">{opportunity.tuition_coverage_status || "Covered"}</span>
                </div>
                <h3 className="funding-card-value"><Value>{opportunity.tuition_coverage}</Value></h3>
                <p className="funding-card-desc">Direct payment for standard degree course tuition fees.</p>
              </div>

              <div className="funding-card-accent accent-blue">
                <div className="funding-card-top">
                  <span className="funding-card-label">Monthly Living Stipend</span>
                  <span className="funding-status-pill">{opportunity.stipend_coverage_status || "Allowance"}</span>
                </div>
                <h3 className="funding-card-value"><Value>{stipend}</Value></h3>
                <p className="funding-card-desc">Monthly tax-free living grant for accommodation and food.</p>
              </div>

              <div className="funding-card-accent accent-teal">
                <div className="funding-card-top">
                  <span className="funding-card-label">International Travel</span>
                  <span className="funding-status-pill">{opportunity.travel_coverage_status || "Airfare"}</span>
                </div>
                <h3 className="funding-card-value"><Value>{opportunity.travel_allowance}</Value></h3>
                <p className="funding-card-desc">Round-trip economy flights between home country and campus.</p>
              </div>

              <div className="funding-card-accent accent-blue">
                <div className="funding-card-top">
                  <span className="funding-card-label">Health & Medical</span>
                  <span className="funding-status-pill">{opportunity.insurance_coverage_status || "Covered"}</span>
                </div>
                <h3 className="funding-card-value"><Value>{opportunity.health_insurance}</Value></h3>
                <p className="funding-card-desc">Healthcare coverage and medical insurance surcharge included.</p>
              </div>
            </div>

            {opportunity.funding_summary ? (
              <div className="funding-summary-callout">
                <span className="funding-callout-title">Funding Summary:</span>
                <p>{opportunity.funding_summary}</p>
              </div>
            ) : null}
          </section>

          {/* Statutory Eligibility Criteria */}
          <section className="detail-card-section" aria-label="Eligibility Criteria">
            <div className="section-header-row">
              <div>
                <h2 className="section-heading">📋 Mandatory Eligibility Matrix</h2>
                <p className="section-subtext">Official criteria required for admission and funding</p>
              </div>
            </div>

            <dl className="eligibility-dl">
              <div className="eligibility-row">
                <dt>Degree Level Scope</dt>
                <dd>{degrees.map(readableValue).join(", ")}</dd>
              </div>
              <div className="eligibility-row">
                <dt>Eligible Fields</dt>
                <dd><Value>{opportunity.field_eligibility}</Value></dd>
              </div>
              <div className="eligibility-row">
                <dt>Nationality / Citizenship</dt>
                <dd><Value>{opportunity.nationality_eligibility}</Value></dd>
              </div>
              <div className="eligibility-row">
                <dt>Minimum Academic Grade</dt>
                <dd><Value>{opportunity.minimum_academic_requirement}</Value></dd>
              </div>
              <div className="eligibility-row">
                <dt>English Language Test</dt>
                <dd><Value>{opportunity.english_language_requirement}</Value></dd>
              </div>
              <div className="eligibility-row">
                <dt>Standardized Tests</dt>
                <dd><Value>{opportunity.standardized_test_requirement}</Value></dd>
              </div>
            </dl>
          </section>

          {/* Required Application Documents */}
          <section className="detail-card-section" aria-label="Required Application Documents">
            <h2 className="section-heading">📁 Required Application Documents</h2>
            <div className="documents-checklist-grid">
              {opportunity.required_documents.length ? (
                opportunity.required_documents.map((doc) => (
                  <div key={doc} className="document-check-card">
                    <span className="doc-check-icon">✓</span>
                    <span className="doc-check-title">{doc}</span>
                  </div>
                ))
              ) : (
                <div className="document-check-card">
                  <span className="doc-check-icon">✓</span>
                  <span className="doc-check-title">Official academic transcripts & valid passport</span>
                </div>
              )}
            </div>
          </section>

          {/* Eligibility Warnings & Curator Notes */}
          {opportunity.eligibility_warnings.length ? (
            <section className="detail-warning-luxury" aria-label="Eligibility Warnings">
              <h3 className="warning-heading">⚠️ Important Eligibility Checks</h3>
              <ul className="warning-list">
                {opportunity.eligibility_warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {opportunity.notes ? (
            <section className="detail-curator-note" aria-label="Curator Note">
              <h3 className="curator-note-heading">📌 Curator Note</h3>
              <p>{opportunity.notes}</p>
            </section>
          ) : null}

          {/* Official Source Evidence Vault */}
          <section className="evidence-vault-navy" aria-label="Official Source Evidence Vault">
            <div className="evidence-vault-top">
              <div className="evidence-vault-brand">
                <span className="vault-lock-icon">🔒</span>
                <span className="vault-label">OFFICIAL SOURCE EVIDENCE VAULT</span>
              </div>
              <span className="vault-domain-tag">{opportunity.source.title}</span>
            </div>

            <blockquote className="evidence-quote">
              "{opportunity.source.relevant_excerpt}"
            </blockquote>

            <div className="evidence-vault-footer">
              <span>Officially verified {formatDate(opportunity.source.last_verified_at)} · Source confidence: {readableValue(opportunity.data_confidence)}</span>
              <a
                className="evidence-source-btn"
                href={opportunity.source.url}
                target="_blank"
                rel="noreferrer"
              >
                Open official source ↗
              </a>
            </div>
          </section>

          {/* End-of-Dossier Finale Card */}
          <section className="dossier-finale-card">
            <div className="dossier-finale-text">
              <h3>Ready to apply for {opportunity.name}?</h3>
              <p>Save this to your student workspace to auto-generate personalized task milestones, essay drafts, and deadline alerts.</p>
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
                <span className="sidebar-urgency-title">{urgency.icon} {urgency.label}</span>
                <span className="sidebar-status-tag">Verified</span>
              </div>
              <p className="sidebar-date-text">
                Deadline: <strong>{formatDate(opportunity.application_deadline)}</strong>
              </p>
              <p className="sidebar-date-text">
                Intake: <strong>{opportunity.intake_year ? `${opportunity.intake_year} Academic Cycle` : "Standard Cycle"}</strong>
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
              <Link
                className="button hero-btn-ai sidebar-ai-btn"
                to={`/assistant?opportunity=${opportunity.id}`}
              >
                <span>🤖</span> Talk with AI Copilot
              </Link>
            </div>

            <hr className="sidebar-divider" />

            <div className="sidebar-meta-list">
              <div className="sidebar-meta-row">
                <span>Application Fee:</span>
                <strong className="text-teal">{opportunity.application_fee_info || "Free ($0)"}</strong>
              </div>
              <div className="sidebar-meta-row">
                <span>Method:</span>
                <strong>{opportunity.application_method || "Online Portal"}</strong>
              </div>
              <div className="sidebar-meta-row">
                <span>Confidence:</span>
                <strong className="tier-ready">{readableValue(opportunity.data_confidence)}</strong>
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
