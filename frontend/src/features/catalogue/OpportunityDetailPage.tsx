import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import { createApplication } from "../workspace/workspace";
import { getOpportunityFamily, isNotFound } from "./catalogue";
import { ScholarshipDetailView } from "./ScholarshipDetailView";
import type { OpportunityFamily } from "./types";

function SaveToTrackerButton({ opportunityId }: { opportunityId: string }) {
  const { user } = useAuth();
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (!user) {
    return (
      <section className="guest-save-cta" aria-label="Save and track this opportunity">
        <div>
          <p className="eyebrow">Keep your research moving</p>
          <h2>Save this scholarship and track your application.</h2>
          <p>Create a student account to keep private notes, deadlines, and application progress together.</p>
        </div>
        <Link className="button button-primary" to="/auth">Create an account to save</Link>
      </section>
    );
  }
  if (user.role !== "student") return null;

  async function save() {
    setIsSaving(true);
    setMessage(null);
    try {
      await createApplication(opportunityId);
      setMessage("Application workspace created. Your source-linked tasks are ready.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save this scholarship.");
    } finally {
      setIsSaving(false);
    }
  }

  return <div className="save-to-tracker"><button className="button button-primary" type="button" onClick={save} disabled={isSaving}>{isSaving ? "Creating..." : "Create application"}</button>{message ? <p className={message.startsWith("Application") ? "form-success" : "form-error"} role="status">{message}</p> : null}</div>;
}

export function OpportunityDetailPage() {
  const { opportunityId } = useParams();
  const [activeId, setActiveId] = useState(opportunityId ?? "");
  const { data: family, error, isLoading, reload } = useServerQuery<OpportunityFamily>(
    opportunityId ?? "missing-opportunity",
    (signal) => getOpportunityFamily(opportunityId!, signal),
    Boolean(opportunityId),
  );

  useEffect(() => {
    if (family && !family.variants.some((variant) => variant.id === activeId)) {
      setActiveId(family.variants[0]?.id ?? "");
    }
  }, [activeId, family]);

  return (
    <main className="detail-page page-width" aria-live="polite" aria-busy={isLoading}>
      <Link className="back-link" to="/catalogue">← Back to scholarships</Link>
      {isLoading ? <div className="catalogue-message">Loading official scholarship profile...</div> : null}
      {!isLoading && error ? (
        <div className="catalogue-message error-message" role="alert">
          <h1>{isNotFound(error) ? "This scholarship is no longer publicly available." : "We could not load this scholarship."}</h1>
          <p>{isNotFound(error) ? "It may have closed or returned to review after its source changed." : error instanceof Error ? error.message : "Please try again."}</p>
          <Link className="button button-primary" to="/catalogue">Return to scholarships</Link>
          {!isNotFound(error) ? <button className="button button-quiet" type="button" onClick={reload}>Try again</button> : null}
        </div>
      ) : null}
      {!isLoading && !error && family && activeId ? (
        <ScholarshipDetailView
          family={family}
          activeId={activeId}
          onActiveIdChange={setActiveId}
          afterDetails={(
            <>
              <SaveToTrackerButton opportunityId={activeId} />
              <section className="save-to-tracker">
                <p>Have a practical application question? Community experiences are never official advice.</p>
                <Link className="button button-quiet" to={`/community?opportunity=${activeId}`}>Discuss this scholarship</Link>
              </section>
              <p className="detail-disclaimer">This information supports your research. It is not an admission, scholarship, or visa prediction.</p>
            </>
          )}
        />
      ) : null}
    </main>
  );
}
