import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useServerQuery } from "../../hooks/useServerQuery";
import { availabilityLabel, catalogueSearch, deadlineLabel, filtersFromSearch, formatDate, readableValue, searchOpportunities } from "./catalogue";
import { defaultCatalogueFilters, type CatalogueAvailability, type CatalogueFilters, type OpportunitySearchResponse, type OpportunitySummary } from "./types";

function OpportunityCard({ opportunity }: { opportunity: OpportunitySummary }) {
  return (
    <article className="opportunity-card">
      <div className="card-topline">
        <span className="verified-badge">{opportunity.verification_freshness === "recent" ? "Recently verified official source" : opportunity.verification_freshness === "recheck_recommended" ? "Official source · recheck recommended" : "Historical official verification"}</span>
        <span className="deadline-label">{deadlineLabel(opportunity.application_deadline)}</span>
      </div>
      <p className="evidence-caption">{opportunity.catalogue_decision_tier === "decision_ready" ? "Structured criteria available" : "Informational record · verify criteria manually"}</p>
      <h2>{opportunity.name}</h2>
      <p className="provider-name">
        {opportunity.provider_name}
        {opportunity.university_name ? ` · ${opportunity.university_name}` : ""}
      </p>
      <div className="tag-list" aria-label="Opportunity summary">
        <span>{opportunity.country}</span>
        <span>{readableValue(opportunity.degree_level)}</span>
        <span>{opportunity.funding_display_label}</span>
      </div>
      <p className="funding-summary">{opportunity.funding_summary}</p>
      <p className="evidence-caption">
        Source last verified {formatDate(opportunity.last_verified_at)}.
      </p>
      <div className="card-actions">
        <Link className="button button-primary" to={`/catalogue/${opportunity.id}`}>
          View opportunity
        </Link>
        <a className="button button-quiet" href={opportunity.official_source_url} target="_blank" rel="noreferrer">
          Official source
        </a>
      </div>
    </article>
  );
}

function CatalogueFiltersForm({
  value,
  onSubmit,
  onClear,
}: {
  value: CatalogueFilters;
  onSubmit: (filters: CatalogueFilters) => void;
  onClear: () => void;
}) {
  const [filters, setFilters] = useState(value);

  useEffect(() => setFilters(value), [value]);

  function update(key: keyof CatalogueFilters, nextValue: string) {
    setFilters((current) => ({ ...current, [key]: nextValue }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(filters);
  }

  return (
    <form className="catalogue-filters" onSubmit={submit} aria-label="Filter verified opportunities">
      <label>
        Availability
        <select value={filters.availability} onChange={(event) => update("availability", event.target.value)} name="availability">
          <option value="open">Open now</option>
          <option value="upcoming">Upcoming</option>
          <option value="all">All verified</option>
        </select>
      </label>
      <label>
        Country
        <input value={filters.country} onChange={(event) => update("country", event.target.value)} placeholder="Malaysia, UK, USA..." name="country" />
      </label>
      <label>
        Degree level
        <select value={filters.degree_level} onChange={(event) => update("degree_level", event.target.value)} name="degree_level">
          <option value="">Any level</option>
          <option value="bachelors">Bachelors</option>
          <option value="masters">Masters</option>
          <option value="phd">PhD</option>
          <option value="postdoc">Postdoc</option>
          <option value="short_course">Short course</option>
        </select>
      </label>
      <label>
        Funding
        <select value={filters.funding_type} onChange={(event) => update("funding_type", event.target.value)} name="funding_type">
          <option value="">Any funding</option>
          <option value="full">Full funding</option>
          <option value="partial">Partial funding</option>
          <option value="tuition_only">Tuition only</option>
          <option value="stipend_only">Stipend only</option>
        </select>
      </label>
      <label>
        Field of study
        <input value={filters.field} onChange={(event) => update("field", event.target.value)} placeholder="Computer science" name="field" />
      </label>
      <label>
        Nationality
        <input value={filters.nationality} onChange={(event) => update("nationality", event.target.value)} placeholder="Pakistan" name="nationality" />
      </label>
      <label>
        Results per page
        <select value={filters.limit} onChange={(event) => update("limit", event.target.value)} name="limit">
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="50">50</option>
        </select>
      </label>
      <div className="filter-actions">
        <button className="button button-primary" type="submit">Apply filters</button>
        <button className="button button-quiet" type="button" onClick={onClear}>Clear</button>
      </div>
    </form>
  );
}

export function CataloguePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => filtersFromSearch(searchParams), [searchParams]);
  const offset = Number(searchParams.get("offset") ?? "0") || 0;
  const { data: results, error: requestError, isLoading, reload } = useServerQuery<OpportunitySearchResponse>(
    searchParams.toString(),
    (signal) => searchOpportunities(filters, offset, signal),
  );
  const error = requestError instanceof Error ? requestError.message : requestError ? "Unable to load opportunities." : null;

  function updateSearch(nextFilters: CatalogueFilters, nextOffset = 0) {
    setSearchParams(catalogueSearch(nextFilters, nextOffset));
  }

  const pagination = results?.pagination;
  const availabilityDetails: Record<CatalogueAvailability, { title: string; description: string; empty: string }> = {
    open: {
      title: "Current openings only",
      description: "Records with an unknown, future, expired, or stale application window are intentionally excluded.",
      empty: "No open verified opportunities match these filters.",
    },
    upcoming: {
      title: "Upcoming verified opportunities",
      description: "These official-source records have a future application opening date. Re-check dates before planning an application.",
      empty: "No upcoming verified opportunities match these filters.",
    },
    all: {
      title: "All verified opportunities",
      description: "Open opportunities appear first, followed by upcoming, deadline-variable, and closed records. Check the displayed window state and source date carefully.",
      empty: "No verified opportunities match these filters.",
    },
  };
  const availabilityDetail = availabilityDetails[filters.availability];
  return (
    <main className="catalogue-page page-width">
      <section className="catalogue-header">
        <div>
          <p className="eyebrow">Verified scholarships</p>
          <h1>Find the opportunities worth your attention.</h1>
          <p className="lead">Every result has an active, officially verified source. Open opportunities appear first, followed by upcoming and deadline-variable records; deadlines and eligibility still need your careful review.</p>
        </div>
        <aside className="catalogue-safety-note">
          <strong>{availabilityDetail.title}</strong>
          <p>{availabilityDetail.description}</p>
        </aside>
      </section>

      <CatalogueFiltersForm value={filters} onSubmit={updateSearch} onClear={() => updateSearch(defaultCatalogueFilters)} />

      <section className="result-section" aria-live="polite" aria-busy={isLoading}>
        <div className="result-heading">
          <div>
            <p className="eyebrow">Search results</p>
            <h2>{isLoading ? "Checking verified sources..." : `${pagination?.total ?? 0} ${availabilityLabel(filters.availability)}`}</h2>
          </div>
          {pagination ? <p className="result-count">Showing {pagination.count} of {pagination.total}</p> : null}
        </div>

        {error ? (
          <div className="catalogue-message error-message" role="alert">
            <h2>We could not load scholarships.</h2>
            <p>{error}</p>
            <button className="button button-quiet" type="button" onClick={reload}>Try again</button>
          </div>
        ) : null}
        {isLoading ? <div className="catalogue-message">Loading verified opportunities...</div> : null}
        {!isLoading && !error && results?.items.length === 0 ? (
          <div className="catalogue-message">
            <h2>{availabilityDetail.empty}</h2>
            <p>Try broadening a filter. Drafts and unverified sources are never included here.</p>
            <button className="button button-quiet" type="button" onClick={() => updateSearch(defaultCatalogueFilters)}>Clear filters</button>
          </div>
        ) : null}
        {!isLoading && !error && results?.items.length ? <div className="opportunity-grid">{results.items.map((opportunity) => <OpportunityCard key={opportunity.id} opportunity={opportunity} />)}</div> : null}
      </section>

      {pagination ? (
        <nav className="pagination" aria-label="Scholarship pagination">
          <button className="button button-quiet" type="button" disabled={!pagination.has_previous} onClick={() => updateSearch(filters, Math.max(0, offset - pagination.limit))}>Previous</button>
          <span>Page {Math.floor(offset / pagination.limit) + 1}</span>
          <button className="button button-quiet" type="button" disabled={!pagination.has_next} onClick={() => updateSearch(filters, offset + pagination.limit)}>Next</button>
        </nav>
      ) : null}
    </main>
  );
}
