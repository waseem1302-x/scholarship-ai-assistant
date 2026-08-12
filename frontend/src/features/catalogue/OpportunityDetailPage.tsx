import { type ReactNode, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { createApplication, saveOpportunity } from "../workspace/workspace";
import { deadlineLabel, formatDate, getOpportunity, isNotFound, readableValue } from "./catalogue";
import type { OpportunityDetail } from "./types";

function Value({ children }: { children: string | number | null | undefined }) {
  return <span>{children === null || children === undefined || children === "" ? "Not stated" : children}</span>;
}

function DetailList({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="detail-list">
      <h2>{title}</h2>
      <dl>{children}</dl>
    </section>
  );
}

function DetailRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd><Value>{value}</Value></dd>
    </div>
  );
}

function OpportunityDetailContent({ opportunity }: { opportunity: OpportunityDetail }) {
  const stipend = opportunity.monthly_stipend_amount
    ? `${opportunity.monthly_stipend_amount.toLocaleString()} ${opportunity.monthly_stipend_currency ?? ""}`.trim()
    : null;
  return (
    <>
      <section className="detail-hero">
        <div>
          <p className="eyebrow">Official-source opportunity detail</p>
          <h1>{opportunity.name}</h1>
          <p className="provider-name">
            {opportunity.provider_name}
            {opportunity.university_name ? ` · ${opportunity.university_name}` : ""}
          </p>
        </div>
        <div className="tag-list detail-tags" aria-label="Opportunity snapshot">
          <span>{opportunity.country}</span>
          <span>{readableValue(opportunity.degree_level)}</span>
          <span>{readableValue(opportunity.funding_type)} funding</span>
          <span>{deadlineLabel(opportunity.application_deadline)}</span>
        </div>
      </section>

      <section className="detail-summary">
        <div>
          <span className="card-kicker">Funding summary</span>
          <p>{opportunity.funding_summary}</p>
        </div>
        <div>
          <span className="card-kicker">Source confidence</span>
          <p>{readableValue(opportunity.data_confidence)} confidence · verified {formatDate(opportunity.last_verified_at)}</p>
        </div>
      </section>

      <div className="detail-grid">
        <DetailList title="Funding package">
          <DetailRow label="Tuition" value={opportunity.tuition_coverage} />
          <DetailRow label="Monthly stipend" value={stipend} />
          <DetailRow label="Accommodation" value={opportunity.accommodation_coverage} />
          <DetailRow label="Travel" value={opportunity.travel_allowance} />
          <DetailRow label="Health insurance" value={opportunity.health_insurance} />
          <DetailRow label="Application fee" value={opportunity.application_fee_info} />
        </DetailList>
        <DetailList title="Eligibility">
          <DetailRow label="Field" value={opportunity.field_eligibility} />
          <DetailRow label="Nationality" value={opportunity.nationality_eligibility} />
          <DetailRow label="Minimum academics" value={opportunity.minimum_academic_requirement} />
          <DetailRow label="English language" value={opportunity.english_language_requirement} />
          <DetailRow label="Standardized tests" value={opportunity.standardized_test_requirement} />
        </DetailList>
        <DetailList title="Application">
          <DetailRow label="Method" value={opportunity.application_method} />
          <DetailRow label="Deadline" value={formatDate(opportunity.application_deadline)} />
          <DetailRow label="Intake year" value={opportunity.intake_year} />
          <div>
            <dt>Application page</dt>
            <dd>{opportunity.application_url ? <a className="detail-link" href={opportunity.application_url} target="_blank" rel="noreferrer">Open application page</a> : "Not stated"}</dd>
          </div>
        </DetailList>
        <DetailList title="Required documents">
          {opportunity.required_documents.length ? opportunity.required_documents.map((document) => <DetailRow key={document} label="Document" value={document} />) : <DetailRow label="Documents" value={null} />}
        </DetailList>
      </div>

      {opportunity.eligibility_warnings.length ? (
        <section className="detail-warning" aria-label="Eligibility warnings">
          <h2>Important eligibility checks</h2>
          <ul>{opportunity.eligibility_warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </section>
      ) : null}
      {opportunity.notes ? (
        <section className="detail-note">
          <h2>Curator note</h2>
          <p>{opportunity.notes}</p>
        </section>
      ) : null}

      <section className="source-evidence">
        <div>
          <p className="eyebrow">Official source evidence</p>
          <h2>{opportunity.source.title}</h2>
          <p>{opportunity.source.relevant_excerpt}</p>
          <p className="evidence-caption">Officially verified {formatDate(opportunity.source.last_verified_at)}. Always confirm current requirements on the source before applying.</p>
        </div>
        <a className="button button-primary" href={opportunity.source.url} target="_blank" rel="noreferrer">Open official source</a>
      </section>
      <p className="detail-disclaimer">This information supports your research. It is not an admission, scholarship, or visa prediction.</p>
    </>
  );
}

function SaveToTrackerButton({ opportunityId }: { opportunityId: string }) {
  const { user } = useAuth();
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (!user) {
    return (
      <section className="guest-save-cta" aria-label="Save and track this opportunity">
        <div>
          <p className="eyebrow">Keep your research moving</p>
          <h2>Save this opportunity and track your application.</h2>
          <p>Create a student account to keep private notes, personal deadlines, and application progress in one place.</p>
        </div>
        <Link className="button button-primary" to="/auth">
          Create an account to save and track
        </Link>
      </section>
    );
  }

  if (user.role !== "student") return null;

  async function save() {
    setIsSaving(true);
    setMessage(null);
    try {
      try { await saveOpportunity(opportunityId); } catch (error) { if (!(error instanceof Error) || !error.message.includes("already saved")) throw error; }
      await createApplication(opportunityId);
      setMessage("Application workspace created. Your source-linked tasks are ready.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save this opportunity.");
    } finally {
      setIsSaving(false);
    }
  }

  return <div className="save-to-tracker"><button className="button button-primary" type="button" onClick={save} disabled={isSaving}>{isSaving ? "Creating..." : "Create application"}</button>{message ? <p className={message.startsWith("Application") ? "form-success" : "form-error"} role="status">{message}</p> : null}</div>;
}

export function OpportunityDetailPage() {
  const { opportunityId } = useParams();
  const [opportunity, setOpportunity] = useState<OpportunityDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!opportunityId) return;
    let active = true;
    setIsLoading(true);
    setError(null);
    void getOpportunity(opportunityId)
      .then((response) => {
        if (active) setOpportunity(response);
      })
      .catch((requestError: unknown) => {
        if (active) setError(requestError);
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [opportunityId]);

  return (
    <main className="detail-page page-width" aria-live="polite" aria-busy={isLoading}>
      <Link className="back-link" to="/catalogue">← Back to catalogue</Link>
      {isLoading ? <div className="catalogue-message">Loading official source evidence...</div> : null}
      {!isLoading && error ? (
        <div className="catalogue-message error-message" role="alert">
          <h1>{isNotFound(error) ? "This opportunity is no longer publicly available." : "We could not load this opportunity."}</h1>
          <p>{isNotFound(error) ? "It may have closed or returned to review after its source changed." : error instanceof Error ? error.message : "Please try again."}</p>
          <Link className="button button-primary" to="/catalogue">Return to catalogue</Link>
        </div>
      ) : null}
      {!isLoading && !error && opportunity ? <OpportunityDetailContent opportunity={opportunity} /> : null}
      {!isLoading && !error && opportunity ? <SaveToTrackerButton opportunityId={opportunity.id} /> : null}
    </main>
  );
}
