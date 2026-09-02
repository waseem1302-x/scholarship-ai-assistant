import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import type { Application, OpportunityMatch } from "../workspace/types";
import { createApplication, getApplications, getMatches } from "../workspace/workspace";
import {
  catalogueSearch,
  filtersFromSearch,
  formatCardDeadline,
  getCountryFlag,
  getDestinationImage,
  getInclusionsSummary,
  getOpportunityBadges,
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
import { degreeOptions, destinationOptions, fundingOptions } from "./searchOptions";

const COMMON_COUNTRIES = destinationOptions.map((option) => option.country);
const DEGREE_OPTIONS = degreeOptions.filter((option) => option.value);
const FUNDING_OPTIONS = fundingOptions.filter((option) => option.value);

const PROVIDER_TYPES = [
  "Government",
  "University",
  "Foundation / Trust",
  "International Organization",
];

const ELIGIBILITY_TYPES = [
  "All International Students",
  "Developing Countries",
  "Commonwealth Citizens",
  "ASEAN Nationals",
];

const DEADLINE_RANGES = [
  "Closing this month",
  "Next 3 months",
  "Next 6 months",
  "Rolling / Open all year",
];

interface FacetCounts {
  countries: Record<string, number>;
  degrees: Record<string, number>;
  fundings: Record<string, number>;
  statuses: {
    open: number;
    upcoming: number;
    closed: number;
  };
}

function calculateFacets(items: OpportunitySummary[]): FacetCounts {
  const facets: FacetCounts = {
    countries: {},
    degrees: {},
    fundings: {},
    statuses: {
      open: 0,
      upcoming: 0,
      closed: 0,
    },
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

    if (item.application_window_state === "open" || (!item.application_deadline && item.verification_status === "officially_verified")) {
      facets.statuses.open += 1;
    } else if (item.application_window_state === "upcoming") {
      facets.statuses.upcoming += 1;
    } else {
      facets.statuses.closed += 1;
    }
  }

  return facets;
}

/* ==========================================================================
   HORIZONTAL SCHOLARSHIP CARD (LIST VIEW)
   ========================================================================== */
function ScholarshipListCard({
  opportunity,
  match,
  isSaved = false,
  onToggleSave,
}: {
  opportunity: OpportunitySummary;
  match?: OpportunityMatch;
  isSaved?: boolean;
  onToggleSave?: (e: React.MouseEvent) => void;
}) {
  const [localSaved, setLocalSaved] = useState(false);
  const [imgError, setImgError] = useState(false);

  const saved = onToggleSave ? isSaved : localSaved;
  const countryFlag = getCountryFlag(opportunity.country);
  const deadlineText = formatCardDeadline(opportunity.application_deadline);
  const badges = getOpportunityBadges(opportunity);
  const inclusions = getInclusionsSummary(opportunity);
  const imageUrl = imgError
    ? "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?auto=format&fit=crop&w=600&q=80"
    : getDestinationImage(opportunity.country, opportunity.name);

  const degreeName = readableValue(opportunity.degree_level);
  const targetScope = opportunity.country ? opportunity.country : "All countries";
  const providerLabel = opportunity.provider_name || opportunity.university_name || "Official Scholarship Body";

  function handleSaveClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (onToggleSave) {
      onToggleSave(e);
    } else {
      setLocalSaved((prev) => !prev);
    }
  }

  return (
    <article className="scholarship-card-list">
      {/* 1. Left Column: Landmark Thumbnail */}
      <div className="scholarship-card-list__media">
        <img
          src={imageUrl}
          alt={`${opportunity.name} destination`}
          loading="lazy"
          onError={() => setImgError(true)}
          className="scholarship-card-list__img"
        />
      </div>

      {/* 2. Middle Column: Info & Details */}
      <div className="scholarship-card-list__body">
        {/* Badges & Bookmark Row */}
        <div className="scholarship-card-list__top">
          <div className="scholarship-card-list__badges">
            <span
              className={
                "scholarship-badge " +
                (badges.fundingBadge.tier === "full"
                  ? "scholarship-badge--full"
                  : "scholarship-badge--partial")
              }
            >
              {badges.fundingBadge.label}
            </span>

            {badges.highlightBadge && (
              <span
                className={
                  "scholarship-badge " +
                  (badges.highlightBadge.style === "top"
                    ? "scholarship-badge--top"
                    : badges.highlightBadge.style === "popular"
                    ? "scholarship-badge--popular"
                    : "scholarship-badge--new")
                }
              >
                {badges.highlightBadge.label}
              </span>
            )}

            {match && (
              <span className="scholarship-badge scholarship-badge--match">
                ✨ {match.fit_score ?? match.match_score}% Match
              </span>
            )}
          </div>

          <button
            type="button"
            className={"scholarship-bookmark-btn " + (saved ? "scholarship-bookmark-btn--saved" : "")}
            onClick={handleSaveClick}
            aria-label={saved ? "Remove from bookmarks" : "Save scholarship"}
            title={saved ? "Saved" : "Save scholarship"}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill={saved ? "#0B4D3C" : "none"} stroke="currentColor" strokeWidth="1.8">
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
            </svg>
          </button>
        </div>

        {/* Title */}
        <h3 className="scholarship-card-list__title">
          <Link to={"/catalogue/" + opportunity.id}>{opportunity.name}</Link>
        </h3>

        {/* Provider Row */}
        <div className="scholarship-card-list__provider">
          <span className="scholarship-card-list__flag">{countryFlag}</span>
          <span className="scholarship-card-list__provider-name">{providerLabel}</span>
        </div>

        {/* Description */}
        <p className="scholarship-card-list__desc">
          {opportunity.funding_summary ||
            `Prestigious scholarship opportunity for ${degreeName} studies in ${targetScope}.`}
        </p>

        {/* Metadata Icons Row */}
        <div className="scholarship-card-list__meta-row">
          <div className="scholarship-card-list__meta-item">
            <span className="scholarship-meta-icon" aria-hidden="true">🎓</span>
            <span>{degreeName.charAt(0).toUpperCase() + degreeName.slice(1)}</span>
          </div>
          <div className="scholarship-card-list__meta-item">
            <span className="scholarship-meta-icon" aria-hidden="true">🌐</span>
            <span>{targetScope}</span>
          </div>
          <div className="scholarship-card-list__meta-item">
            <span className="scholarship-meta-icon" aria-hidden="true">📅</span>
            <span>{deadlineText}</span>
          </div>
        </div>
      </div>

      {/* 3. Right Column: Financial Highlights & Action */}
      <div className="scholarship-card-list__action-col">
        <div className="scholarship-card-list__funding-summary">
          <span className="scholarship-card-list__funding-head">
            {badges.fundingBadge.label}
          </span>
          <span className="scholarship-card-list__funding-sub">
            {inclusions}
          </span>
        </div>

        <Link
          to={"/catalogue/" + opportunity.id}
          className="scholarship-cta-btn"
        >
          <span>View details</span>
          <span className="scholarship-cta-arrow">→</span>
        </Link>
      </div>
    </article>
  );
}

/* ==========================================================================
   GRID VARIANT FOR VIEW TOGGLE
   ========================================================================== */
function ScholarshipGridCard({
  opportunity,
  match,
  isSaved = false,
  onToggleSave,
}: {
  opportunity: OpportunitySummary;
  match?: OpportunityMatch;
  isSaved?: boolean;
  onToggleSave?: (e: React.MouseEvent) => void;
}) {
  const [localSaved, setLocalSaved] = useState(false);
  const [imgError, setImgError] = useState(false);

  const saved = onToggleSave ? isSaved : localSaved;
  const countryFlag = getCountryFlag(opportunity.country);
  const deadlineText = formatCardDeadline(opportunity.application_deadline);
  const badges = getOpportunityBadges(opportunity);
  const inclusions = getInclusionsSummary(opportunity);
  const imageUrl = imgError
    ? "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?auto=format&fit=crop&w=600&q=80"
    : getDestinationImage(opportunity.country, opportunity.name);

  const degreeName = readableValue(opportunity.degree_level);
  const targetScope = opportunity.country ? opportunity.country : "All countries";
  const providerLabel = opportunity.provider_name || opportunity.university_name || "Official Scholarship Body";

  function handleSaveClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (onToggleSave) {
      onToggleSave(e);
    } else {
      setLocalSaved((prev) => !prev);
    }
  }

  return (
    <article className="scholarship-card-grid">
      <div className="scholarship-card-grid__media">
        <img
          src={imageUrl}
          alt={`${opportunity.name} destination`}
          loading="lazy"
          onError={() => setImgError(true)}
          className="scholarship-card-grid__img"
        />
        <button
          type="button"
          className={"scholarship-bookmark-btn scholarship-bookmark-btn--floating " + (saved ? "scholarship-bookmark-btn--saved" : "")}
          onClick={handleSaveClick}
          aria-label="Save scholarship"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill={saved ? "#0B4D3C" : "none"} stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
          </svg>
        </button>
      </div>

      <div className="scholarship-card-grid__content">
        <div className="scholarship-card-list__badges">
          <span
            className={
              "scholarship-badge " +
              (badges.fundingBadge.tier === "full"
                ? "scholarship-badge--full"
                : "scholarship-badge--partial")
            }
          >
            {badges.fundingBadge.label}
          </span>
          {badges.highlightBadge && (
            <span
              className={
                "scholarship-badge " +
                (badges.highlightBadge.style === "top"
                  ? "scholarship-badge--top"
                  : badges.highlightBadge.style === "popular"
                  ? "scholarship-badge--popular"
                  : "scholarship-badge--new")
              }
            >
              {badges.highlightBadge.label}
            </span>
          )}
          {match && (
            <span className="scholarship-badge scholarship-badge--match">
              ✨ {match.fit_score ?? match.match_score}%
            </span>
          )}
        </div>

        <h3 className="scholarship-card-grid__title">
          <Link to={"/catalogue/" + opportunity.id}>{opportunity.name}</Link>
        </h3>

        <div className="scholarship-card-list__provider">
          <span>{countryFlag}</span>
          <span className="scholarship-card-list__provider-name">{providerLabel}</span>
        </div>

        <div className="scholarship-card-grid__meta">
          <span>🎓 {degreeName}</span>
          <span>🌐 {targetScope}</span>
          <span>📅 {deadlineText}</span>
        </div>

        <div className="scholarship-card-grid__footer">
          <div className="scholarship-card-grid__inclusions">{inclusions}</div>
          <Link to={"/catalogue/" + opportunity.id} className="scholarship-cta-btn scholarship-cta-btn--full">
            <span>View details</span>
            <span>→</span>
          </Link>
        </div>
      </div>
    </article>
  );
}

/* ==========================================================================
   SKELETON LOADER
   ========================================================================== */
function ScholarshipSkeletonCard({ isGrid = false }: { isGrid?: boolean }) {
  if (isGrid) {
    return (
      <article className="scholarship-card-grid scholarship-card--skeleton" aria-hidden="true">
        <div className="scholarship-skeleton-block" style={{ width: "100%", height: 160 }} />
        <div className="scholarship-card-grid__content">
          <div className="scholarship-skeleton-line" style={{ width: "40%", height: 20 }} />
          <div className="scholarship-skeleton-line" style={{ width: "85%", height: 22, margin: "10px 0" }} />
          <div className="scholarship-skeleton-line" style={{ width: "60%", height: 16 }} />
          <div className="scholarship-skeleton-line" style={{ width: "100%", height: 38, marginTop: 14, borderRadius: 10 }} />
        </div>
      </article>
    );
  }

  return (
    <article className="scholarship-card-list scholarship-card--skeleton" aria-hidden="true">
      <div className="scholarship-card-list__media">
        <div className="scholarship-skeleton-block" style={{ width: "100%", height: "100%", minHeight: 120 }} />
      </div>
      <div className="scholarship-card-list__body">
        <div className="scholarship-skeleton-line" style={{ width: "30%", height: 20 }} />
        <div className="scholarship-skeleton-line" style={{ width: "70%", height: 24, margin: "8px 0" }} />
        <div className="scholarship-skeleton-line" style={{ width: "40%", height: 16, marginBottom: 8 }} />
        <div className="scholarship-skeleton-line" style={{ width: "90%", height: 14, marginBottom: 12 }} />
        <div className="scholarship-skeleton-line" style={{ width: "60%", height: 16 }} />
      </div>
      <div className="scholarship-card-list__action-col">
        <div className="scholarship-skeleton-line" style={{ width: "80%", height: 18 }} />
        <div className="scholarship-skeleton-line" style={{ width: "100%", height: 14 }} />
        <div className="scholarship-skeleton-line" style={{ width: "100%", height: 38, borderRadius: 10 }} />
      </div>
    </article>
  );
}

/* ==========================================================================
   MAIN CATALOGUE PAGE
   ========================================================================== */
export function CataloguePage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => filtersFromSearch(searchParams), [searchParams]);
  const offset = Number(searchParams.get("offset") ?? "0") || 0;
  const sortBy = searchParams.get("sort_by") ?? "deadline";
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  // Additional sidebar filter selections
  const [selectedProviderTypes, setSelectedProviderTypes] = useState<string[]>([]);
  const [selectedEligibilities, setSelectedEligibilities] = useState<string[]>([]);
  const [selectedDeadlineRanges, setSelectedDeadlineRanges] = useState<string[]>([]);

  // Collapsible Accordion states
  const [accordionOpen, setAccordionOpen] = useState({
    country: true,
    field: false,
    provider: false,
    eligibility: false,
    deadline: false,
  });

  const toggleAccordion = (key: keyof typeof accordionOpen) => {
    setAccordionOpen((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // Local state for top search bar
  const [searchInput, setSearchInput] = useState({
    field: filters.field,
    country: filters.country,
    degree_level: filters.degree_level,
    funding_type: filters.funding_type,
  });

  useEffect(() => {
    setSearchInput({
      field: filters.field,
      country: filters.country,
      degree_level: filters.degree_level,
      funding_type: filters.funding_type,
    });
  }, [filters]);

  const { data: results, error: requestError, isLoading, reload } = useServerQuery<OpportunitySearchResponse>(
    searchParams.toString(),
    (signal) => searchOpportunities(filters, offset, signal),
  );

  const { data: studentMatches } = useServerQuery<OpportunityMatch[]>(
    user?.id ?? "anonymous",
    (signal) => getMatches(signal),
    user?.role === "student",
  );

  const { data: userApplications, reload: reloadApps } = useServerQuery<Application[]>(
    user?.id ? `apps-${user.id}` : "no-user-apps",
    (signal) => getApplications(signal),
    user?.role === "student",
  );

  const [localSavedIds, setLocalSavedIds] = useState<Set<string>>(() => new Set<string>());

  const savedSet = useMemo(() => {
    const set = new Set(localSavedIds);
    if (userApplications) {
      for (const app of userApplications) {
        set.add(app.opportunity.id);
      }
    }
    return set;
  }, [localSavedIds, userApplications]);

  async function handleToggleSave(oppId: string) {
    if (user?.role === "student") {
      if (!savedSet.has(oppId)) {
        try {
          await createApplication(oppId);
          reloadApps();
        } catch {
          // ignore or fallback
        }
      }
    }
    setLocalSavedIds((prev) => {
      const next = new Set(prev);
      if (next.has(oppId)) next.delete(oppId);
      else next.add(oppId);
      return next;
    });
  }

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

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    updateSearch(
      {
        ...filters,
        country: searchInput.country.trim(),
        degree_level: searchInput.degree_level,
        field: searchInput.field.trim(),
        funding_type: searchInput.funding_type,
      },
      0
    );
  }

  function handleStatusChange(status: CatalogueAvailability) {
    updateSearch({ ...filters, availability: status }, 0);
  }

  function toggleFilter(key: keyof CatalogueFilters, value: string) {
    const current = filters[key];
    const next = current === value ? "" : value;
    updateSearch({ ...filters, [key]: next }, 0);
  }

  function resetAllFilters() {
    setSelectedProviderTypes([]);
    setSelectedEligibilities([]);
    setSelectedDeadlineRanges([]);
    updateSearch(defaultCatalogueFilters, 0);
  }

  const pagination = results?.pagination;
  const totalCount = pagination?.total ?? 0;
  const totalPages = pagination ? Math.max(1, Math.ceil(pagination.total / pagination.limit)) : 1;
  const currentPage = pagination ? Math.floor(offset / pagination.limit) + 1 : 1;

  // Filter and sort items
  const items = useMemo(() => {
    let list = [...(results?.items ?? [])];

    // Client-side text keyword search refinement if user typed a keyword that matches name/provider
    if (filters.field) {
      const q = filters.field.toLowerCase();
      list = list.filter((item) => {
        const name = (item.name || "").toLowerCase();
        const provider = (item.provider_name || "").toLowerCase();
        const uni = (item.university_name || "").toLowerCase();
        const summary = (item.funding_summary || "").toLowerCase();
        return name.includes(q) || provider.includes(q) || uni.includes(q) || summary.includes(q);
      });
    }

    // Provider type filter
    if (selectedProviderTypes.length > 0) {
      list = list.filter((item) => {
        const text = (item.name + " " + (item.provider_name || "") + " " + (item.university_name || "")).toLowerCase();
        return selectedProviderTypes.some((p) => {
          if (p === "Government") return text.includes("government") || text.includes("chevening") || text.includes("daad") || text.includes("fulbright") || text.includes("mext");
          if (p === "University") return text.includes("university") || text.includes("college") || text.includes("institute");
          if (p === "Foundation / Trust") return text.includes("foundation") || text.includes("trust") || text.includes("fellowship");
          if (p === "International Organization") return text.includes("union") || text.includes("erasmus") || text.includes("world bank") || text.includes("unesco");
          return true;
        });
      });
    }

    // Eligibility filter
    if (selectedEligibilities.length > 0) {
      list = list.filter((item) => {
        const text = (item.name + " " + (item.funding_summary || "")).toLowerCase();
        return selectedEligibilities.some((e) => {
          if (e === "Developing Countries") return text.includes("developing") || text.includes("epos") || text.includes("commonwealth");
          if (e === "Commonwealth Citizens") return text.includes("commonwealth");
          if (e === "ASEAN Nationals") return text.includes("asean") || text.includes("singa");
          return true;
        });
      });
    }

    // Deadline range filter
    if (selectedDeadlineRanges.length > 0) {
      const now = Date.now();
      list = list.filter((item) => {
        if (!item.application_deadline) return selectedDeadlineRanges.includes("Rolling / Open all year");
        const deadlineTs = new Date(item.application_deadline).getTime();
        const daysDiff = (deadlineTs - now) / 86400000;
        return selectedDeadlineRanges.some((r) => {
          if (r === "Closing this month") return daysDiff >= 0 && daysDiff <= 31;
          if (r === "Next 3 months") return daysDiff >= 0 && daysDiff <= 92;
          if (r === "Next 6 months") return daysDiff >= 0 && daysDiff <= 184;
          if (r === "Rolling / Open all year") return !item.application_deadline || daysDiff > 184;
          return true;
        });
      });
    }

    // Sorting
    if (sortBy === "name") {
      list.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === "verified") {
      list.sort((a, b) => new Date(b.last_verified_at ?? 0).getTime() - new Date(a.last_verified_at ?? 0).getTime());
    } else if (sortBy === "funding") {
      const rank = (f?: string) => (f === "full" ? 4 : f === "partial" ? 3 : f === "tuition_only" ? 2 : f === "stipend_only" ? 1 : 0);
      list.sort((a, b) => rank(b.funding_type) - rank(a.funding_type));
    } else if (sortBy === "deadline") {
      list.sort((a, b) => {
        if (!a.application_deadline) return 1;
        if (!b.application_deadline) return -1;
        return new Date(a.application_deadline).getTime() - new Date(b.application_deadline).getTime();
      });
    }

    return list;
  }, [results?.items, filters.field, selectedProviderTypes, selectedEligibilities, selectedDeadlineRanges, sortBy]);

  // Clean and accurate display count
  const displayCount = results ? (selectedProviderTypes.length > 0 || selectedEligibilities.length > 0 || selectedDeadlineRanges.length > 0 || filters.field ? items.length : totalCount) : 0;

  return (
    <main className="scholarship-page-wrapper">
      <div className="scholarship-page-container">
        
        {/* ==================================================================
            1. HERO SECTION WITH SAGE BACKGROUND & WORLD MAP WATERMARK
            ================================================================== */}
        <section className="scholarship-hero" aria-label="Scholarship banner">
          <div className="scholarship-hero__content">
            <span className="scholarship-hero__eyebrow">GLOBAL OPPORTUNITIES</span>
            <h1 className="scholarship-hero__title">Find scholarships for your future</h1>
            <p className="scholarship-hero__subtitle">
              Explore 500+ verified scholarships from top governments, universities and organizations around the world.
            </p>
          </div>

          {/* Floating live daily notification pill on the right */}
          <div className="scholarship-hero__pill">
            <span className="scholarship-hero__pill-icon">🎓</span>
            <span className="scholarship-hero__pill-badge">New</span>
            <span className="scholarship-hero__pill-text">Opportunities added daily</span>
            <span className="scholarship-hero__pill-arrow">→</span>
          </div>

          {/* Background SVG World Map Graphic */}
          <div className="scholarship-hero__map-bg" aria-hidden="true">
            <svg viewBox="0 0 600 300" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M80 70c20-20 60-15 80 0s30 40 10 60-50 20-70 0-30-50-20-60zm140 20c30-10 80 0 90 20s-10 40-40 45-60-20-60-40 0-20 10-25zm160-30c40-15 100 10 120 40s-20 70-60 70-70-30-75-60 0-40 15-50zM120 180c25-10 50 15 45 35s-30 40-55 30-30-35-15-50 20-10 25-15zm320-10c30-10 70 20 60 50s-45 50-75 40-40-40-20-65 20-20 35-25z"
                fill="currentColor"
              />
            </svg>
          </div>
        </section>

        {/* ==================================================================
            2. UNIFIED FLOATING SEARCH BAR & MULTI-DROPDOWN CONTROLS
            ================================================================== */}
        <section className="scholarship-search-container" aria-label="Search and quick filters">
          <form className="scholarship-search-bar" onSubmit={handleSearchSubmit}>
            {/* Search Keyword Input */}
            <div className="scholarship-search-bar__input-wrap">
              <span className="scholarship-search-bar__icon">🔍</span>
              <input
                type="text"
                placeholder="Search scholarships, universities or keywords..."
                value={searchInput.field}
                onChange={(e) => setSearchInput((s) => ({ ...s, field: e.target.value }))}
                className="scholarship-search-bar__input"
                aria-label="Search query"
              />
            </div>

            <div className="scholarship-search-bar__divider" />

            {/* Country Dropdown */}
            <div className="scholarship-search-bar__select-wrap">
              <select
                value={searchInput.country}
                onChange={(e) => setSearchInput((s) => ({ ...s, country: e.target.value }))}
                className="scholarship-search-bar__select"
                aria-label="Filter by country"
              >
                <option value="">Any country</option>
                {COMMON_COUNTRIES.map((c) => (
                  <option key={c} value={c}>
                    {getCountryFlag(c)} {c}
                  </option>
                ))}
              </select>
            </div>

            <div className="scholarship-search-bar__divider" />

            {/* Degree Dropdown */}
            <div className="scholarship-search-bar__select-wrap">
              <select
                value={searchInput.degree_level}
                onChange={(e) => setSearchInput((s) => ({ ...s, degree_level: e.target.value as DegreeLevel }))}
                className="scholarship-search-bar__select"
                aria-label="Filter by degree"
              >
                <option value="">Any degree</option>
                {DEGREE_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="scholarship-search-bar__divider" />

            {/* Funding Dropdown */}
            <div className="scholarship-search-bar__select-wrap">
              <select
                value={searchInput.funding_type}
                onChange={(e) => setSearchInput((s) => ({ ...s, funding_type: e.target.value as FundingType }))}
                className="scholarship-search-bar__select"
                aria-label="Filter by funding"
              >
                <option value="">Any funding</option>
                {FUNDING_OPTIONS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Submit Button */}
            <button type="submit" className="scholarship-search-bar__submit">
              Search
            </button>
          </form>
        </section>

        {/* ==================================================================
            3. MAIN WORKSPACE: SIDEBAR FILTERS + RESULTS AREA
            ================================================================== */}
        <div className="scholarship-layout">
          
          {/* LEFT SIDEBAR: FACET FILTERS */}
          <aside className="scholarship-sidebar" aria-label="Filters">
            <div className="scholarship-sidebar__header">
              <h2 className="scholarship-sidebar__title">Filters</h2>
              <button
                type="button"
                className="scholarship-sidebar__reset"
                onClick={resetAllFilters}
              >
                Reset
              </button>
            </div>

            {/* Status (Radio list) */}
            <div className="scholarship-filter-section">
              <h3 className="scholarship-filter-section__title">Status</h3>
              <div className="scholarship-radio-group">
                <label className="scholarship-radio-row">
                  <span className="scholarship-radio-row__left">
                    <input
                      type="radio"
                      name="scholarship-status"
                      checked={filters.availability === "all"}
                      onChange={() => handleStatusChange("all")}
                      className="scholarship-radio-input"
                    />
                    <span className="scholarship-radio-label">All opportunities</span>
                  </span>
                </label>

                <label className="scholarship-radio-row">
                  <span className="scholarship-radio-row__left">
                    <input
                      type="radio"
                      name="scholarship-status"
                      checked={filters.availability === "open"}
                      onChange={() => handleStatusChange("open")}
                      className="scholarship-radio-input"
                    />
                    <span className="scholarship-radio-label">Open now</span>
                  </span>
                  {facetCounts.statuses.open > 0 && (
                    <span className="scholarship-radio-count">({facetCounts.statuses.open})</span>
                  )}
                </label>

                <label className="scholarship-radio-row">
                  <span className="scholarship-radio-row__left">
                    <input
                      type="radio"
                      name="scholarship-status"
                      checked={filters.availability === "upcoming"}
                      onChange={() => handleStatusChange("upcoming")}
                      className="scholarship-radio-input"
                    />
                    <span className="scholarship-radio-label">Opening soon</span>
                  </span>
                  {facetCounts.statuses.upcoming > 0 && (
                    <span className="scholarship-radio-count">({facetCounts.statuses.upcoming})</span>
                  )}
                </label>
              </div>
            </div>

            {/* Degree Level (Checkboxes) */}
            <div className="scholarship-filter-section">
              <h3 className="scholarship-filter-section__title">Degree level</h3>
              <div className="scholarship-checkbox-group">
                {DEGREE_OPTIONS.map((deg) => {
                  const count = facetCounts.degrees[deg.value];
                  return (
                    <label key={deg.value} className="scholarship-checkbox-row">
                      <span className="scholarship-checkbox-row__left">
                        <input
                          type="checkbox"
                          checked={filters.degree_level === deg.value}
                          onChange={() => toggleFilter("degree_level", deg.value)}
                          className="scholarship-checkbox-input"
                        />
                        <span>{deg.label}</span>
                      </span>
                      {count !== undefined && count > 0 && (
                        <span className="scholarship-checkbox-count">({count})</span>
                      )}
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Funding Type (Checkboxes) */}
            <div className="scholarship-filter-section">
              <h3 className="scholarship-filter-section__title">Funding type</h3>
              <div className="scholarship-checkbox-group">
                {FUNDING_OPTIONS.map((fund) => {
                  const count = facetCounts.fundings[fund.value];
                  return (
                    <label key={fund.value} className="scholarship-checkbox-row">
                      <span className="scholarship-checkbox-row__left">
                        <input
                          type="checkbox"
                          checked={filters.funding_type === fund.value}
                          onChange={() => toggleFilter("funding_type", fund.value)}
                          className="scholarship-checkbox-input"
                        />
                        <span>{fund.label}</span>
                      </span>
                      {count !== undefined && count > 0 && (
                        <span className="scholarship-checkbox-count">({count})</span>
                      )}
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Collapsible Accordion: Country / Region */}
            <div className="scholarship-accordion">
              <button
                type="button"
                className="scholarship-accordion__trigger"
                onClick={() => toggleAccordion("country")}
                aria-expanded={accordionOpen.country}
              >
                <span>Country / Region</span>
                <span className={"scholarship-accordion__chevron " + (accordionOpen.country ? "scholarship-accordion__chevron--open" : "")}>
                  ⌵
                </span>
              </button>
              {accordionOpen.country && (
                <div className="scholarship-accordion__content">
                  {COMMON_COUNTRIES.slice(0, 6).map((c) => {
                    const isSelected = filters.country.toLowerCase() === c.toLowerCase();
                    const count = facetCounts.countries[c];
                    return (
                      <label key={c} className="scholarship-checkbox-row">
                        <span className="scholarship-checkbox-row__left">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleFilter("country", c)}
                            className="scholarship-checkbox-input"
                          />
                          <span>{getCountryFlag(c)} {c}</span>
                        </span>
                        {count !== undefined && count > 0 && (
                          <span className="scholarship-checkbox-count">({count})</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Collapsible Accordion: Field of Study */}
            <div className="scholarship-accordion">
              <button
                type="button"
                className="scholarship-accordion__trigger"
                onClick={() => toggleAccordion("field")}
                aria-expanded={accordionOpen.field}
              >
                <span>Field of study</span>
                <span className={"scholarship-accordion__chevron " + (accordionOpen.field ? "scholarship-accordion__chevron--open" : "")}>
                  ⌵
                </span>
              </button>
              {accordionOpen.field && (
                <div className="scholarship-accordion__content">
                  <input
                    type="text"
                    placeholder="e.g. Computer Science, Economics"
                    value={filters.field}
                    onChange={(e) => updateSearch({ ...filters, field: e.target.value }, 0)}
                    className="scholarship-accordion-input"
                  />
                </div>
              )}
            </div>

            {/* Collapsible Accordion: Provider type */}
            <div className="scholarship-accordion">
              <button
                type="button"
                className="scholarship-accordion__trigger"
                onClick={() => toggleAccordion("provider")}
                aria-expanded={accordionOpen.provider}
              >
                <span>Provider type</span>
                <span className={"scholarship-accordion__chevron " + (accordionOpen.provider ? "scholarship-accordion__chevron--open" : "")}>
                  ⌵
                </span>
              </button>
              {accordionOpen.provider && (
                <div className="scholarship-accordion__content">
                  {PROVIDER_TYPES.map((p) => (
                    <label key={p} className="scholarship-checkbox-row">
                      <span className="scholarship-checkbox-row__left">
                        <input
                          type="checkbox"
                          checked={selectedProviderTypes.includes(p)}
                          onChange={() => {
                            setSelectedProviderTypes((prev) =>
                              prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
                            );
                          }}
                          className="scholarship-checkbox-input"
                        />
                        <span>{p}</span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* Collapsible Accordion: Eligibility */}
            <div className="scholarship-accordion">
              <button
                type="button"
                className="scholarship-accordion__trigger"
                onClick={() => toggleAccordion("eligibility")}
                aria-expanded={accordionOpen.eligibility}
              >
                <span>Eligibility</span>
                <span className={"scholarship-accordion__chevron " + (accordionOpen.eligibility ? "scholarship-accordion__chevron--open" : "")}>
                  ⌵
                </span>
              </button>
              {accordionOpen.eligibility && (
                <div className="scholarship-accordion__content">
                  {ELIGIBILITY_TYPES.map((e) => (
                    <label key={e} className="scholarship-checkbox-row">
                      <span className="scholarship-checkbox-row__left">
                        <input
                          type="checkbox"
                          checked={selectedEligibilities.includes(e)}
                          onChange={() => {
                            setSelectedEligibilities((prev) =>
                              prev.includes(e) ? prev.filter((x) => x !== e) : [...prev, e]
                            );
                          }}
                          className="scholarship-checkbox-input"
                        />
                        <span>{e}</span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* Collapsible Accordion: Deadline range */}
            <div className="scholarship-accordion">
              <button
                type="button"
                className="scholarship-accordion__trigger"
                onClick={() => toggleAccordion("deadline")}
                aria-expanded={accordionOpen.deadline}
              >
                <span>Deadline range</span>
                <span className={"scholarship-accordion__chevron " + (accordionOpen.deadline ? "scholarship-accordion__chevron--open" : "")}>
                  ⌵
                </span>
              </button>
              {accordionOpen.deadline && (
                <div className="scholarship-accordion__content">
                  {DEADLINE_RANGES.map((d) => (
                    <label key={d} className="scholarship-checkbox-row">
                      <span className="scholarship-checkbox-row__left">
                        <input
                          type="checkbox"
                          checked={selectedDeadlineRanges.includes(d)}
                          onChange={() => {
                            setSelectedDeadlineRanges((prev) =>
                              prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]
                            );
                          }}
                          className="scholarship-checkbox-input"
                        />
                        <span>{d}</span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </aside>

          {/* RIGHT COLUMN: RESULTS TOOLBAR + CARDS LIST */}
          <section className="scholarship-results-area" aria-live="polite" aria-busy={isLoading}>
            
            {/* Results Toolbar: Found Count + Sort Dropdown + View Toggle */}
            <div className="scholarship-results-toolbar">
              <h2 className="scholarship-results-toolbar__count">
                {isLoading ? "Loading scholarships..." : `${displayCount} scholarships found`}
              </h2>

              <div className="scholarship-results-toolbar__actions">
                <div className="scholarship-sort-control">
                  <span className="scholarship-sort-label">Sort by:</span>
                  <select
                    value={sortBy}
                    onChange={(e) => updateSearch(filters, 0, e.target.value)}
                    className="scholarship-sort-select"
                    aria-label="Sort scholarships by"
                  >
                    <option value="deadline">Deadline (soonest)</option>
                    <option value="verified">Recently verified</option>
                    <option value="funding">Full funding first</option>
                    <option value="name">Alphabetical (A–Z)</option>
                  </select>
                </div>

                {/* View Mode Toggle: List (☰) vs Grid (⊞) */}
                <div className="scholarship-view-toggle" role="group" aria-label="View style">
                  <button
                    type="button"
                    className={"scholarship-view-btn " + (viewMode === "list" ? "scholarship-view-btn--active" : "")}
                    onClick={() => setViewMode("list")}
                    aria-label="List view"
                    title="List view"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className={"scholarship-view-btn " + (viewMode === "grid" ? "scholarship-view-btn--active" : "")}
                    onClick={() => setViewMode("grid")}
                    aria-label="Grid view"
                    title="Grid view"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            {/* Error state */}
            {error && (
              <div className="scholarship-alert-box scholarship-alert-box--error" role="alert">
                <h3>We could not load scholarships.</h3>
                <p>{error}</p>
                <button type="button" onClick={reload} className="scholarship-cta-btn">
                  Try again
                </button>
              </div>
            )}

            {/* Loading skeletons */}
            {isLoading && (
              <div className={viewMode === "grid" ? "scholarship-cards-grid" : "scholarship-cards-list"}>
                <ScholarshipSkeletonCard isGrid={viewMode === "grid"} />
                <ScholarshipSkeletonCard isGrid={viewMode === "grid"} />
                <ScholarshipSkeletonCard isGrid={viewMode === "grid"} />
                <ScholarshipSkeletonCard isGrid={viewMode === "grid"} />
              </div>
            )}

            {/* Empty State */}
            {!isLoading && !error && items.length === 0 && (
              <div className="scholarship-empty-state">
                <div className="scholarship-empty-state__icon">🔍</div>
                <h3>No scholarships match your filters.</h3>
                <p>Try clearing some criteria or searching for different keywords.</p>
                <button
                  type="button"
                  className="scholarship-cta-btn"
                  onClick={resetAllFilters}
                >
                  Clear all filters
                </button>
              </div>
            )}

            {/* Main Cards List / Grid */}
            {!isLoading && !error && items.length > 0 && (
              <div className={viewMode === "grid" ? "scholarship-cards-grid" : "scholarship-cards-list"}>
                {items.map((opportunity) =>
                  viewMode === "grid" ? (
                    <ScholarshipGridCard
                      key={opportunity.id}
                      opportunity={opportunity}
                      match={matchMap.get(opportunity.id)}
                      isSaved={savedSet.has(opportunity.id)}
                      onToggleSave={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        void handleToggleSave(opportunity.id);
                      }}
                    />
                  ) : (
                    <ScholarshipListCard
                      key={opportunity.id}
                      opportunity={opportunity}
                      match={matchMap.get(opportunity.id)}
                      isSaved={savedSet.has(opportunity.id)}
                      onToggleSave={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        void handleToggleSave(opportunity.id);
                      }}
                    />
                  )
                )}
              </div>
            )}

            {/* ==============================================================
                4. PAGINATION FOOTER
                ============================================================== */}
            {pagination && totalPages > 1 && (
              <nav className="scholarship-pagination-bar" aria-label="Pagination">
                <div className="scholarship-pagination-controls">
                  <button
                    type="button"
                    className="scholarship-pagination-arrow"
                    disabled={!pagination.has_previous}
                    onClick={() => updateSearch(filters, Math.max(0, offset - pagination.limit))}
                    aria-label="Previous page"
                  >
                    ←
                  </button>

                  <div className="scholarship-pagination-pages">
                    {Array.from({ length: totalPages }, (_, i) => i + 1)
                      .filter((p) => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 2)
                      .map((p, idx, arr) => {
                        const prev = arr[idx - 1];
                        const showEllipsis = prev && p - prev > 1;
                        return (
                          <span key={p} className="scholarship-pagination-num-wrap">
                            {showEllipsis && <span className="scholarship-pagination-ellipsis">…</span>}
                            <button
                              type="button"
                              className={
                                "scholarship-pagination-page-btn " +
                                (p === currentPage ? "scholarship-pagination-page-btn--active" : "")
                              }
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
                    type="button"
                    className="scholarship-pagination-arrow"
                    disabled={!pagination.has_next}
                    onClick={() => updateSearch(filters, offset + pagination.limit)}
                    aria-label="Next page"
                  >
                    →
                  </button>
                </div>

                <div className="scholarship-pagination-summary">
                  Showing {offset + 1}–{Math.min(offset + (pagination.limit || 10), totalCount)} of {totalCount} scholarships
                </div>
              </nav>
            )}

          </section>

        </div>

      </div>
    </main>
  );
}
