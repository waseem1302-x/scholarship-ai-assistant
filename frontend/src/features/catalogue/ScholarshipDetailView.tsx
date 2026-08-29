import type { ReactNode } from "react";

import { deadlineLabel, formatDate, readableValue } from "./catalogue";

export interface ScholarshipDetailRecord {
  id: string;
  university_name: string | null;
  country: string;
  degree_level: string;
  degree_levels?: string[];
  intake_year: number | null;
  application_deadline: string | null;
  application_opening_date: string | null;
  funding_display_label: string;
  funding_summary: string;
  tuition_coverage: string | null;
  tuition_coverage_status?: string;
  monthly_stipend_amount: number | null;
  monthly_stipend_currency: string | null;
  stipend_coverage_status?: string;
  accommodation_coverage: string | null;
  accommodation_coverage_status?: string;
  travel_allowance: string | null;
  travel_coverage_status?: string;
  health_insurance: string | null;
  insurance_coverage_status?: string;
  application_fee_info: string | null;
  nationality_eligibility: string | null;
  field_eligibility: string | null;
  minimum_academic_requirement: string | null;
  english_language_requirement: string | null;
  standardized_test_requirement: string | null;
  application_method: string | null;
  application_url: string | null;
  required_documents: string[];
  eligibility_warnings: string[];
  notes: string | null;
  last_verified_at: string | null;
  source: {
    id: string;
    url: string;
    title: string;
    relevant_excerpt: string;
    last_verified_at: string | null;
  };
}

export interface ScholarshipDetailFamily {
  family_key: string;
  name: string;
  provider_name: string;
  country: string;
  degree_levels: string[];
  variants: ScholarshipDetailRecord[];
}

function hasValue(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  return !["unknown", "not stated"].includes(String(value).trim().toLowerCase());
}

function DetailList({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return <section className="detail-list premium-detail-section" id={id}><h2>{title}</h2><dl>{children}</dl></section>;
}

function DetailRow({ label, value, optional = false }: { label: string; value: string | number | null | undefined; optional?: boolean }) {
  const known = hasValue(value);
  return <div className={known ? "detail-value-known" : "detail-value-missing"}><dt>{label}</dt><dd>{known ? value : optional ? "Not stated" : "Unknown — verify from official source"}</dd></div>;
}

function coverageLabel(status: string | undefined, detail: string | null | undefined): string {
  if (hasValue(detail)) return String(detail);
  if (status === "confirmed") return "Confirmed by source; exact amount not stated";
  if (status === "not_covered") return "Not covered";
  if (status === "partial") return "Partially covered";
  return "Unknown — verify from official source";
}

function variantLabel(opportunity: ScholarshipDetailRecord): string {
  const levels = opportunity.degree_levels?.length ? opportunity.degree_levels : [opportunity.degree_level];
  return levels.map(readableValue).join(" + ");
}

export interface ScholarshipDetailViewProps {
  family: ScholarshipDetailFamily;
  activeId: string;
  onActiveIdChange: (id: string) => void;
  beforeDetails?: ReactNode;
  afterDetails?: ReactNode;
}

export function ScholarshipDetailView({ family, activeId, onActiveIdChange, beforeDetails, afterDetails }: ScholarshipDetailViewProps) {
  const opportunity = family.variants.find((variant) => variant.id === activeId) ?? family.variants[0];
  if (!opportunity) return null;
  const stipend = opportunity.monthly_stipend_amount
    ? `${opportunity.monthly_stipend_amount.toLocaleString()} ${opportunity.monthly_stipend_currency ?? ""} monthly`.trim()
    : null;
  const activeLevels = opportunity.degree_levels?.length ? opportunity.degree_levels : [opportunity.degree_level];

  return <>
    <section className="detail-hero premium-detail-hero">
      <div>
        <p className="eyebrow">Official-source scholarship</p>
        <h1>{family.name}</h1>
        <p className="provider-name">{family.provider_name}{opportunity.university_name ? ` · ${opportunity.university_name}` : ""}</p>
        <p className="detail-intro">One complete scholarship profile. Choose a study level below to see its exact funding, eligibility, deadline and application route.</p>
      </div>
      <div className="detail-trust-card"><span className="verified-badge">Official source</span><strong>{opportunity.funding_display_label}</strong><small>Verified {formatDate(opportunity.last_verified_at)}</small></div>
    </section>

    <nav className="detail-anchor-nav" aria-label="Scholarship sections"><a href="#overview">Overview</a><a href="#funding">Funding</a><a href="#eligibility">Eligibility</a><a href="#application">Application</a><a href="#evidence">Evidence</a></nav>

    <section className="degree-switcher" id="overview" aria-label="Available study levels"><div><p className="eyebrow">Available study routes</p><h2>{family.degree_levels.length} level{family.degree_levels.length === 1 ? "" : "s"} on one page</h2></div><div className="degree-option-list">{family.variants.map((variant) => <button key={variant.id} type="button" className={variant.id === opportunity.id ? "degree-option is-active" : "degree-option"} onClick={() => onActiveIdChange(variant.id)} aria-pressed={variant.id === opportunity.id}><strong>{variantLabel(variant)}</strong><span>{variant.intake_year ? `${variant.intake_year} intake` : "Intake not stated"}</span><small>{deadlineLabel(variant.application_deadline)}</small></button>)}</div></section>

    <section className="detail-summary premium-detail-summary"><div><span className="card-kicker">Selected route</span><p>{activeLevels.map(readableValue).join(", ")} · {opportunity.country}</p></div><div><span className="card-kicker">Funding</span><p>{opportunity.funding_summary}</p></div><div><span className="card-kicker">Application window</span><p>{deadlineLabel(opportunity.application_deadline)}</p></div></section>

    {beforeDetails}

    <div className="detail-grid premium-detail-grid">
      <DetailList id="funding" title="Funding package"><DetailRow label="Tuition" value={coverageLabel(opportunity.tuition_coverage_status, opportunity.tuition_coverage)} /><DetailRow label="Monthly stipend" value={coverageLabel(opportunity.stipend_coverage_status, stipend)} /><DetailRow label="Accommodation" value={coverageLabel(opportunity.accommodation_coverage_status, opportunity.accommodation_coverage)} optional /><DetailRow label="Travel" value={coverageLabel(opportunity.travel_coverage_status, opportunity.travel_allowance)} optional /><DetailRow label="Health insurance" value={coverageLabel(opportunity.insurance_coverage_status, opportunity.health_insurance)} optional /><DetailRow label="Application fee" value={opportunity.application_fee_info} optional /></DetailList>
      <DetailList id="eligibility" title="Who can apply"><DetailRow label="Nationality" value={opportunity.nationality_eligibility} /><DetailRow label="Field of study" value={opportunity.field_eligibility} /><DetailRow label="Minimum academics" value={opportunity.minimum_academic_requirement} /><DetailRow label="English language" value={opportunity.english_language_requirement} /><DetailRow label="Standardized tests" value={opportunity.standardized_test_requirement} optional /></DetailList>
      <DetailList id="application" title="How to apply"><DetailRow label="Opening date" value={formatDate(opportunity.application_opening_date)} optional /><DetailRow label="Deadline" value={formatDate(opportunity.application_deadline)} /><DetailRow label="Intake year" value={opportunity.intake_year} optional /><DetailRow label="Method" value={opportunity.application_method} /><div className={opportunity.application_url ? "detail-value-known" : "detail-value-missing"}><dt>Application page</dt><dd>{opportunity.application_url ? <a className="detail-link" href={opportunity.application_url} target="_blank" rel="noreferrer">Open application page ↗</a> : "Unknown — verify from official source"}</dd></div></DetailList>
      <DetailList id="documents" title="Required documents">{opportunity.required_documents.length ? opportunity.required_documents.map((document) => <DetailRow key={document} label="Document" value={document} />) : <DetailRow label="Documents" value={null} />}</DetailList>
    </div>

    {opportunity.eligibility_warnings.length ? <section className="detail-warning"><p className="eyebrow">Before you apply</p><h2>Important checks</h2><ul>{opportunity.eligibility_warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></section> : null}
    {opportunity.notes ? <section className="detail-note"><h2>Curator note</h2><p>{opportunity.notes}</p></section> : null}
    <section className="source-evidence premium-source-evidence" id="evidence"><div><p className="eyebrow">Official source evidence</p><h2>{opportunity.source.title}</h2><p>{opportunity.source.relevant_excerpt}</p><p className="evidence-caption">Verified {formatDate(opportunity.source.last_verified_at)}. Unknown fields stay unknown until a current official source supports them.</p></div><a className="button button-primary" href={opportunity.source.url} target="_blank" rel="noreferrer">Open official source ↗</a></section>
    {afterDetails}
  </>;
}
