import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import type { OpportunityMatch } from "../workspace/types";
import { getMatches } from "../workspace/workspace";
import {
  availabilityLabel,
  catalogueSearch,
  filtersFromSearch,
  getCountryFlag,
  getDeadlineUrgency,
  readableValue,
  searchOpportunities,
} from "./catalogue";
import {
  defaultCatalogueFilters,
  type CatalogueAvailability,
  type CatalogueFilters,
  type DegreeLevel,
  type FundingType,
  type OpportunitySearchResponse,
  type OpportunitySummary,
} from "./types";

interface FacetCounts {
  countries: Record<string, number>;
  degrees: Record<string, number>;
  fundings: Record<string, number>;
}

function calculateFacets(items: OpportunitySummary[]): FacetCounts {
  const facets: FacetCounts = {
    countries: {},
    degrees: {},
    fundings: {},
  };

  for (const item of items) {
    if (item.country) {
      facets.countries[item.country] = (facets.countries[item.country] ?? 0) + 1;
    }
    const degrees = item.degree_levels?.length ? item.degree_levels : item.degree_level ? [item.degree_level] : [];
    for (const d of degrees) {
      facets.degrees[d] = (facets.degrees[d] ?? 0) + 1;
    }
    if (item.funding_type) {
      facets.fundings[item.funding_type] = (facets.fundings[item.funding_type] ?? 0) + 1;
    }
  }

  return facets;
}

function SkeletonCard() {
  return (
    <article className="opportunity-card skeleton-card" aria-hidden="true">
      <div className="card-topline">
        <span className="skeleton-line skeleton-badge" />
        <span className="skeleton-line skeleton-pill" />
      </div>
      <div className="skeleton-line skeleton-title" />
      <div className="skeleton-line skeleton-subtitle" />
      <div className="tag-list">
        <span className="skeleton-line skeleton-tag" />
        <span className="skeleton-line skeleton-tag" />
        <span className="skeleton-line skeleton-tag" />
      </div>
      <div className="skeleton-line skeleton-funding" />
      <div className="card-actions">
        <span className="skeleton-line skeleton-btn" />
        <span className="skeleton-line skeleton-link" />
      </div>
      <div className="skeleton-line skeleton-footer" />
    </article>
  );
}

function MatchFooter({ match, userRole }: { match?: OpportunityMatch; userRole?: string }) {
  if (userRole === "student" && match) {
    const score = match.fit_score ?? match.match_score;
    const isHardFailure = match.eligibility_status === "ineligible" || match.eligibility_status === "likely_ineligible";

    if (isHardFailure) {
      return (
        <div className="card-match-footer match-footer-blocked">
          <span className="match-footer-icon">⚠️</span>
          <span className="match-footer-text">Hard eligibility barrier · Review criteria</span>
        </div>
      );
    }

    if (score >= 80) {
      return (
        <div className="card-match-footer match-footer-high">
          <span className="match-footer-icon">✨</span>
          <span className="match-footer-text">
            <strong>{score}% Match</strong> · Strong fit for your profile
          </span>
          <span className="match-dot" aria-hidden="true" />
        </div>
      );
    }

    if (score >= 60) {
      return (
        <div className="card-match-footer match-footer-good">
          <span className="match-footer-icon">✦</span>
          <span className="match-footer-text">
            <strong>{score}% Match</strong> · Good fit for your profile
          </span>
        </div>
      );
    }

    return (
      <div className="card-match-footer match-footer-partial">
        <span className="match-footer-icon">⚠️</span>
        <span className="match-footer-text">
          <strong>{score}% Match</strong> · Needs requirement check
        </span>
      </div>
    );
  }

  if (userRole === "student") {
    return (
      <Link to="/profile" className="card-match-footer match-footer-cta">
        <span className="match-footer-icon">✨</span>
        <span className="match-footer-text">Complete your profile to view match score ➔</span>
      </Link>
    );
  }

  return (
    <Link to="/auth" className="card-match-footer match-footer-cta">
      <span className="match-footer-icon">✨</span>
      <span className="match-footer-text">Sign in to check your profile match score ➔</span>
    </Link>
  );
}

function OpportunityCard({
  opportunity,
  match,
  userRole,
}: {
  opportunity: OpportunitySummary;
  match?: OpportunityMatch;
  userRole?: string;
}) {
  const urgency = getDeadlineUrgency(opportunity.application_deadline);
  const countryFlag = getCountryFlag(opportunity.country);
  const degrees = opportunity.degree_levels?.length ? opportunity.degree_levels : [opportunity.degree_level];

  return (
    <article className="opportunity-card">
      <div className="card-topline">
        <span className="verified-badge">✓ Verified</span>
        <div className="topline-right">
          <span className={`urgency-pill urgency-${urgency.tier}`}>
            <span className="urgency-icon" aria-hidden="true">{urgency.icon}</span>
            {urgency.label}
          </span>
          <button type="button" className="bookmark-btn" aria-label={`Save ${opportunity.name} to tracker`} title="Save opportunity">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        </div>
      </div>

      <h2 className="card-title">
        <Link to={`/catalogue/${opportunity.id}`}>{opportunity.name}</Link>
      </h2>

      <p className="provider-name">
        {opportunity.provider_name}
        {opportunity.university_name ? ` · ${opportunity.university_name}` : ""}
      </p>

      <div className="tag-list" aria-label="Opportunity tags">
        <span className="tag-country">
          <span aria-hidden="true">{countryFlag}</span> {opportunity.country || "Global"}
        </span>
        {degrees.filter(Boolean).map((deg) => (
          <span key={deg} className="tag-degree">
            {readableValue(deg)}
          </span>
        ))}
        {opportunity.funding_display_label ? (
          <span className="tag-funding">{opportunity.funding_display_label}</span>
        ) : null}
      </div>

      <p className="funding-summary">
        <span className="funding-icon" aria-hidden="true">💰</span>
        {opportunity.funding_summary || opportunity.funding_display_label || "Funding details available"}
      </p>

      <div className="card-actions">
        <Link className="button button-primary" to={`/catalogue/${opportunity.id}`}>
          View details
        </Link>
        {opportunity.official_source_url ? (
          <a className="official-source-link" href={opportunity.official_source_url} target="_blank" rel="noreferrer">
            Official source ↗
          </a>
        ) : null}
      </div>

      <MatchFooter match={match} userRole={userRole} />
    </article>
  );
}

const COMMON_COUNTRIES = [
  "Malaysia",
  "United Kingdom",
  "Japan",
  "Australia",
  "United States",
  "Canada",
  "Germany",
  "Singapore",
  "Netherlands",
];

const DEGREE_OPTIONS: { value: DegreeLevel; label: string }[] = [
  { value: "masters", label: "Masters" },
  { value: "phd", label: "PhD" },
  { value: "bachelors", label: "Bachelors" },
  { value: "postdoc", label: "Postdoc" },
  { value: "short_course", label: "Short course" },
];

const FUNDING_OPTIONS: { value: FundingType; label: string }[] = [
  { value: "full", label: "Full funding" },
  { value: "partial", label: "Partial funding" },
  { value: "tuition_only", label: "Tuition only" },
  { value: "stipend_only", label: "Stipend only" },
];

export function CataloguePage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => filtersFromSearch(searchParams), [searchParams]);
  const offset = Number(searchParams.get("offset") ?? "0") || 0;
  const sortBy = searchParams.get("sort_by") ?? "deadline";

  // Temporary local state for search inputs
  const [searchInput, setSearchInput] = useState({
    country: filters.country,
    degree_level: filters.degree_level,
    field: filters.field,
    funding_type: filters.funding_type,
  });

  // Country sidebar search
  const [countrySearch, setCountrySearch] = useState("");
  const [showAllCountries, setShowAllCountries] = useState(false);

  // Mobile drawer state
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  useEffect(() => {
    setSearchInput({
      country: filters.country,
      degree_level: filters.degree_level,
      field: filters.field,
      funding_type: filters.funding_type,
    });
  }, [filters]);

  const { data: results, error: requestError, isLoading, reload } = useServerQuery<OpportunitySearchResponse>(
    searchParams.toString(),
    (signal) => searchOpportunities(filters, offset, signal),
  );

  // Fetch matches for student users
  const { data: studentMatches } = useServerQuery<OpportunityMatch[]>(
    user?.id ?? "anonymous",
    (signal) => getMatches(signal),
    user?.role === "student",
  );

  const matchMap = useMemo(() => {
    const map = new Map<string, OpportunityMatch>();
    if (studentMatches) {
      for (const m of studentMatches) {
        map.set(m.opportunity.id, m);
      }
    }
    return map;
  }, [studentMatches]);

  const facetCounts = useMemo(() => {
    return calculateFacets(results?.items ?? []);
  }, [results?.items]);

  const error = requestError instanceof Error ? requestError.message : requestError ? "Unable to load opportunities." : null;

  function updateSearch(nextFilters: CatalogueFilters, nextOffset = 0, nextSort = sortBy) {
    const params = catalogueSearch(nextFilters, nextOffset);
    if (nextSort && nextSort !== "deadline") {
      params.set("sort_by", nextSort);
    }
    setSearchParams(params);
  }

  function handleCapsuleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    updateSearch({
      ...filters,
      country: searchInput.country.trim(),
      degree_level: searchInput.degree_level,
      field: searchInput.field.trim(),
      funding_type: searchInput.funding_type,
    }, 0);
  }

  function toggleFilter(key: keyof CatalogueFilters, value: string) {
    const current = filters[key];
    const next = current === value ? "" : value;
    updateSearch({ ...filters, [key]: next }, 0);
  }

  function removeFilter(key: keyof CatalogueFilters) {
    updateSearch({ ...filters, [key]: defaultCatalogueFilters[key] }, 0);
  }

  const pagination = results?.pagination;
  const items = useMemo(() => {
    const list = [...(results?.items ?? [])];
    if (sortBy === "name") {
      list.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === "verified") {
      list.sort((a, b) => new Date(b.last_verified_at ?? 0).getTime() - new Date(a.last_verified_at ?? 0).getTime());
    } else if (sortBy === "funding") {
      const rank = (f?: string) => (f === "full" ? 4 : f === "partial" ? 3 : f === "tuition_only" ? 2 : f === "stipend_only" ? 1 : 0);
      list.sort((a, b) => rank(b.funding_type) - rank(a.funding_type));
    }
    return list;
  }, [results?.items, sortBy]);

  const activeChips: { key: keyof CatalogueFilters; label: string; icon: string }[] = [];
  if (filters.country) activeChips.push({ key: "country", label: filters.country, icon: getCountryFlag(filters.country) });
  if (filters.degree_level) activeChips.push({ key: "degree_level", label: readableValue(filters.degree_level), icon: "🎓" });
  if (filters.field) activeChips.push({ key: "field", label: filters.field, icon: "📖" });
  if (filters.funding_type) activeChips.push({ key: "funding_type", label: readableValue(filters.funding_type), icon: "💰" });
  if (filters.nationality) activeChips.push({ key: "nationality", label: `Nationality: ${filters.nationality}`, icon: "🛂" });
  if (filters.availability !== "open") activeChips.push({ key: "availability", label: availabilityLabel(filters.availability), icon: "●" });

  const displayedCountries = useMemo(() => {
    let list = COMMON_COUNTRIES;
    if (countrySearch.trim()) {
      const q = countrySearch.toLowerCase();
      list = list.filter((c) => c.toLowerCase().includes(q));
    }
    return showAllCountries ? list : list.slice(0, 5);
  }, [countrySearch, showAllCountries]);

  const totalPages = pagination ? Math.max(1, Math.ceil(pagination.total / pagination.limit)) : 1;
  const currentPage = pagination ? Math.floor(offset / pagination.limit) + 1 : 1;

  const availabilityDetails: Record<CatalogueAvailability, { title: string; description: string; empty: string }> = {
    open: {
      title: "Current openings only",
      description: "Records with an unknown, future, expired, or stale application window are intentionally excluded.",
      empty: "No open verified opportunities match these filters.",
    },
    upcoming: {
      title: "Upcoming verified opportunities",
      description: "These official-source records have a future application opening date. Re-check dates before planning.",
      empty: "No upcoming verified opportunities match these filters.",
    },
    all: {
      title: "All verified opportunities",
      description: "Open opportunities appear first, followed by upcoming, deadline-variable, and closed records.",
      empty: "No verified opportunities match these filters.",
    },
  };
  const availabilityDetail = availabilityDetails[filters.availability];

  return (
    <main className="catalogue-page page-width">
      <section className="catalogue-header">
        <div>
          <p className="eyebrow">Verified scholarships</p>
          <h1>Find opportunities worth your attention.</h1>
          <p className="lead">Every result has an active, officially verified source. Explore by destination, degree, and funding.</p>
        </div>
        <aside className="catalogue-safety-note">
          <strong>✓ {availabilityDetail.title}</strong>
          <p>{availabilityDetail.description}</p>
        </aside>
      </section>

      <form className="catalogue-search-capsule" onSubmit={handleCapsuleSubmit} aria-label="Search verified scholarships">
        <div className="search-field">
          <span className="field-icon" aria-hidden="true">📍</span>
          <input
            type="text"
            value={searchInput.country}
            onChange={(e) => setSearchInput((s) => ({ ...s, country: e.target.value }))}
            placeholder="Where (country/region)"
            aria-label="Country or region"
          />
        </div>
        <div className="search-field">
          <span className="field-icon" aria-hidden="true">🎓</span>
          <select
            value={searchInput.degree_level}
            onChange={(e) => setSearchInput((s) => ({ ...s, degree_level: e.target.value as DegreeLevel }))}
            aria-label="Degree level"
          >
            <option value="">Any level</option>
            <option value="masters">Masters</option>
            <option value="phd">PhD</option>
            <option value="bachelors">Bachelors</option>
            <option value="postdoc">Postdoc</option>
            <option value="short_course">Short course</option>
          </select>
        </div>
        <div className="search-field">
          <span className="field-icon" aria-hidden="true">📖</span>
          <input
            type="text"
            value={searchInput.field}
            onChange={(e) => setSearchInput((s) => ({ ...s, field: e.target.value }))}
            placeholder="Field of study"
            aria-label="Field of study"
          />
        </div>
        <div className="search-field">
          <span className="field-icon" aria-hidden="true">💰</span>
          <select
            value={searchInput.funding_type}
            onChange={(e) => setSearchInput((s) => ({ ...s, funding_type: e.target.value as FundingType }))}
            aria-label="Funding type"
          >
            <option value="">Any funding</option>
            <option value="full">Full funding</option>
            <option value="partial">Partial funding</option>
            <option value="tuition_only">Tuition only</option>
            <option value="stipend_only">Stipend only</option>
          </select>
        </div>
        <button type="submit" className="capsule-search-btn">
          Search
        </button>
      </form>

      {activeChips.length > 0 ? (
        <div className="filter-chips-rail" aria-label="Active filters">
          <div className="filter-chips-list">
            {activeChips.map((chip) => (
              <span key={chip.key} className="filter-chip">
                <span aria-hidden="true">{chip.icon}</span> {chip.label}
                <button
                  type="button"
                  className="filter-chip-remove"
                  onClick={() => removeFilter(chip.key)}
                  aria-label={`Remove filter ${chip.label}`}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
          <button
            type="button"
            className="filter-clear-all"
            onClick={() => updateSearch(defaultCatalogueFilters, 0)}
          >
            Clear all
          </button>
        </div>
      ) : null}

      <div className="catalogue-layout-grid">
        <aside className={`catalogue-sidebar ${mobileFilterOpen ? "mobile-drawer-open" : ""}`} aria-label="Refine results">
          <div className="sidebar-header">
            <h2>Refine</h2>
            <button
              type="button"
              className="sidebar-close-mobile"
              onClick={() => setMobileFilterOpen(false)}
              aria-label="Close filters drawer"
            >
              ✕
            </button>
          </div>

          <div className="sidebar-group">
            <h3 className="sidebar-heading">Availability</h3>
            <div className="radio-group">
              <label className="radio-label">
                <input
                  type="radio"
                  name="availability"
                  checked={filters.availability === "open"}
                  onChange={() => updateSearch({ ...filters, availability: "open" }, 0)}
                />
                <span>Open now</span>
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  name="availability"
                  checked={filters.availability === "upcoming"}
                  onChange={() => updateSearch({ ...filters, availability: "upcoming" }, 0)}
                />
                <span>Upcoming</span>
              </label>
              <label className="radio-label">
                <input
                  type="radio"
                  name="availability"
                  checked={filters.availability === "all"}
                  onChange={() => updateSearch({ ...filters, availability: "all" }, 0)}
                />
                <span>All verified</span>
              </label>
            </div>
          </div>

          <hr className="sidebar-divider" />

          <div className="sidebar-group">
            <h3 className="sidebar-heading">Country</h3>
            <div className="sidebar-mini-search">
              <span aria-hidden="true">🔍</span>
              <input
                type="text"
                placeholder="Search country..."
                value={countrySearch}
                onChange={(e) => setCountrySearch(e.target.value)}
                aria-label="Search country in filters"
              />
            </div>
            <div className="checkbox-list">
              {displayedCountries.map((country) => {
                const count = facetCounts.countries[country];
                const checked = filters.country.toLowerCase() === country.toLowerCase();
                return (
                  <label key={country} className="filter-checkbox-row">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleFilter("country", country)}
                    />
                    <span className="checkbox-text">
                      <span aria-hidden="true">{getCountryFlag(country)}</span> {country}
                    </span>
                    {count !== undefined && count > 0 ? (
                      <span className="filter-count-badge">({count})</span>
                    ) : null}
                  </label>
                );
              })}
              {COMMON_COUNTRIES.length > 5 ? (
                <button
                  type="button"
                  className="sidebar-more-link"
                  onClick={() => setShowAllCountries((s) => !s)}
                >
                  {showAllCountries ? "− Show less" : `+ ${COMMON_COUNTRIES.length - 5} more countries`}
                </button>
              ) : null}
            </div>
          </div>

          <hr className="sidebar-divider" />

          <div className="sidebar-group">
            <h3 className="sidebar-heading">Degree level</h3>
            <div className="checkbox-list">
              {DEGREE_OPTIONS.map((opt) => {
                const count = facetCounts.degrees[opt.value];
                const checked = filters.degree_level === opt.value;
                return (
                  <label key={opt.value} className="filter-checkbox-row">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleFilter("degree_level", opt.value)}
                    />
                    <span className="checkbox-text">{opt.label}</span>
                    {count !== undefined && count > 0 ? (
                      <span className="filter-count-badge">({count})</span>
                    ) : null}
                  </label>
                );
              })}
            </div>
          </div>

          <hr className="sidebar-divider" />

          <div className="sidebar-group">
            <h3 className="sidebar-heading">Funding</h3>
            <div className="checkbox-list">
              {FUNDING_OPTIONS.map((opt) => {
                const count = facetCounts.fundings[opt.value];
                const checked = filters.funding_type === opt.value;
                return (
                  <label key={opt.value} className="filter-checkbox-row">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleFilter("funding_type", opt.value)}
                    />
                    <span className="checkbox-text">{opt.label}</span>
                    {count !== undefined && count > 0 ? (
                      <span className="filter-count-badge">({count})</span>
                    ) : null}
                  </label>
                );
              })}
            </div>
          </div>

          <hr className="sidebar-divider" />

          <div className="sidebar-group">
            <h3 className="sidebar-heading">Sort by</h3>
            <select
              className="sidebar-select"
              value={sortBy}
              onChange={(e) => updateSearch(filters, 0, e.target.value)}
              aria-label="Sort opportunities"
            >
              <option value="deadline">Deadline (soonest)</option>
              <option value="verified">Recently verified</option>
              <option value="funding">Funding coverage</option>
              <option value="name">Alphabetical (A–Z)</option>
            </select>
          </div>
        </aside>

        <section className="catalogue-content" aria-live="polite" aria-busy={isLoading}>
          <div className="result-heading">
            <div>
              <h2>{isLoading ? "Checking verified sources..." : `${pagination?.total ?? 0} ${availabilityLabel(filters.availability)}`}</h2>
            </div>
            {pagination && pagination.total > 0 ? (
              <p className="result-count">
                Showing {Math.min(offset + 1, pagination.total)}–{Math.min(offset + pagination.limit, pagination.total)} of {pagination.total}
              </p>
            ) : null}
          </div>

          {error ? (
            <div className="catalogue-message error-message" role="alert">
              <h2>We could not load scholarships.</h2>
              <p>{error}</p>
              <button className="button button-quiet" type="button" onClick={reload}>Try again</button>
            </div>
          ) : null}

          {isLoading ? (
            <div className="opportunity-grid">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : null}

          {!isLoading && !error && items.length === 0 ? (
            <div className="catalogue-message">
              <h2>{availabilityDetail.empty}</h2>
              <p>Try broadening a filter. Drafts and unverified sources are never included here.</p>
              <button className="button button-quiet" type="button" onClick={() => updateSearch(defaultCatalogueFilters)}>
                Clear filters
              </button>
            </div>
          ) : null}

          {!isLoading && !error && items.length > 0 ? (
            <div className="opportunity-grid">
              {items.map((opportunity) => (
                <OpportunityCard
                  key={opportunity.id}
                  opportunity={opportunity}
                  match={matchMap.get(opportunity.id)}
                  userRole={user?.role}
                />
              ))}
            </div>
          ) : null}

          {pagination && totalPages > 1 ? (
            <nav className="pagination-numbered" aria-label="Scholarship page navigation">
              <button
                className="pagination-nav-btn"
                type="button"
                disabled={!pagination.has_previous}
                onClick={() => updateSearch(filters, Math.max(0, offset - pagination.limit))}
              >
                ← Previous
              </button>

              <div className="page-numbers">
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter((p) => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 2)
                  .map((p, idx, arr) => {
                    const prev = arr[idx - 1];
                    const showEllipsis = prev && p - prev > 1;
                    return (
                      <span key={p} className="page-number-wrapper">
                        {showEllipsis ? <span className="pagination-ellipsis">…</span> : null}
                        <button
                          type="button"
                          className={`page-number-btn ${p === currentPage ? "page-number-active" : ""}`}
                          onClick={() => updateSearch(filters, (p - 1) * pagination.limit)}
                          aria-current={p === currentPage ? "page" : undefined}
                        >
                          {p}
                        </button>
                      </span>
                    );
                  })}
              </div>

              <button
                className="pagination-nav-btn"
                type="button"
                disabled={!pagination.has_next}
                onClick={() => updateSearch(filters, offset + pagination.limit)}
              >
                Next →
              </button>
            </nav>
          ) : null}
        </section>
      </div>

      <button
        type="button"
        className="mobile-filter-fab"
        onClick={() => setMobileFilterOpen(true)}
        aria-label="Open filter options"
      >
        <span aria-hidden="true">🔍</span> Filters
      </button>
    </main>
  );
}
