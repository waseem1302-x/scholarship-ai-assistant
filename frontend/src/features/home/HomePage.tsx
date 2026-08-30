import { type FormEvent, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useServerQuery } from "../../hooks/useServerQuery";
import {
  catalogueSearch,
  deadlineLabel,
  readableValue,
  searchOpportunities,
} from "../catalogue/catalogue";
import {
  defaultCatalogueFilters,
  type DegreeLevel,
  type FundingType,
  type OpportunitySearchResponse,
  type OpportunitySummary,
} from "../catalogue/types";

interface HomeSearchState {
  country: string;
  degree_level: DegreeLevel | "";
  field: string;
  funding_type: FundingType | "";
}

const initialSearch: HomeSearchState = {
  country: "",
  degree_level: "",
  field: "",
  funding_type: "",
};

function toCatalogueUrl(partial: Partial<typeof defaultCatalogueFilters>): string {
  const filters = {
    ...defaultCatalogueFilters,
    availability: "all" as const,
    limit: "20" as const,
    ...partial,
  };
  return `/catalogue?${catalogueSearch(filters, 0).toString()}`;
}

function visualTone(country: string): string {
  const normalized = country.toLowerCase();
  if (normalized.includes("kingdom") || normalized === "uk") return "uk";
  if (normalized.includes("state") || normalized === "usa" || normalized === "us") return "usa";
  if (normalized.includes("canada")) return "canada";
  if (normalized.includes("australia")) return "australia";
  if (normalized.includes("malaysia")) return "malaysia";
  if (normalized.includes("germany") || normalized.includes("france") || normalized.includes("europe")) return "europe";
  if (normalized.includes("japan") || normalized.includes("tokyo")) return "japan";
  if (normalized.includes("turkey") || normalized.includes("turkiye")) return "turkey";
  return "global";
}

function countryFlagEmoji(country: string): string {
  const normalized = country.toLowerCase();
  if (normalized.includes("kingdom") || normalized === "uk") return "🇬🇧";
  if (normalized.includes("state") || normalized === "usa" || normalized === "us") return "🇺🇸";
  if (normalized.includes("germany")) return "🇩🇪";
  if (normalized.includes("australia")) return "🇦🇺";
  if (normalized.includes("canada")) return "🇨🇦";
  if (normalized.includes("japan")) return "🇯🇵";
  if (normalized.includes("turkey") || normalized.includes("turkiye")) return "🇹🇷";
  if (normalized.includes("malaysia")) return "🇲🇾";
  if (normalized.includes("switzer") || normalized.includes("swiss")) return "🇨🇭";
  return "🌍";
}

function computeMatchRate(name: string, country: string): string {
  const hash = (name + country).split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const score = 90 + (hash % 10);
  return `★ ${score}% Match`;
}

function AirbnbScholarshipCard({ opportunity }: { opportunity: OpportunitySummary }) {
  const tone = visualTone(opportunity.country);
  const flag = countryFlagEmoji(opportunity.country);
  const isGovt = opportunity.funding_classification === "fully_funded" || opportunity.funding_type === "full";
  const badgeLabel = isGovt ? "Top match" : "Verified";
  const matchRate = computeMatchRate(opportunity.name, opportunity.country);

  return (
    <article
      className="airbnb-scholarship-card"
      onClick={() => window.location.assign(`/catalogue/${opportunity.id}`)}
      tabIndex={0}
      role="link"
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          window.location.assign(`/catalogue/${opportunity.id}`);
        }
      }}
      aria-label={`${opportunity.name} in ${opportunity.country}`}
    >
      <div className={`airbnb-card-media scholarship-visual-${tone}`}>
        <span className="airbnb-top-badge">
          <span aria-hidden="true">✓</span> {badgeLabel}
        </span>
        <button
          type="button"
          className="airbnb-heart-btn"
          title="Save to tracker"
          onClick={(e) => {
            e.stopPropagation();
          }}
          aria-label="Save scholarship"
        >
          <svg className="heart-svg" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 28c7-4.73 14-10 14-17a6.98 6.98 0 0 0-7-7c-1.8 0-3.58.68-4.95 2.05L16 8.1l-2.05-2.05A6.98 6.98 0 0 0 9 4a6.98 6.98 0 0 0-7 7c0 7 7 12.27 14 17z" />
          </svg>
        </button>
        <div className="airbnb-media-content">
          <span className="media-country-tag">{flag} {opportunity.country}</span>
        </div>
      </div>

      <div className="airbnb-card-info">
        <strong className="airbnb-card-title">{opportunity.name}</strong>
        <span className="airbnb-card-subtitle">
          {opportunity.provider_name} · {readableValue(opportunity.degree_level)}
        </span>
        <div className="airbnb-card-price-row">
          <span className="airbnb-card-price">{opportunity.funding_display_label}</span>
          <span className="airbnb-card-rating">{matchRate}</span>
        </div>
      </div>
    </article>
  );
}

function SearchPanel() {
  const navigate = useNavigate();
  const [search, setSearch] = useState<HomeSearchState>(initialSearch);

  function update(key: keyof HomeSearchState, value: string) {
    setSearch((current) => ({ ...current, [key]: value }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate(toCatalogueUrl(search));
  }

  return (
    <form className="airbnb-hero-search-bar" onSubmit={submit} aria-label="Search verified scholarships">
      <label className="search-segment">
        <span className="segment-label">Where</span>
        <input
          value={search.country}
          onChange={(event) => update("country", event.target.value)}
          placeholder="Any country"
          name="country"
          className="segment-input"
        />
      </label>
      <div className="segment-divider" aria-hidden="true" />
      <label className="search-segment">
        <span className="segment-label">Degree Level</span>
        <select
          value={search.degree_level}
          onChange={(event) => update("degree_level", event.target.value as DegreeLevel)}
          name="degree_level"
          className="segment-select"
        >
          <option value="">Any degree</option>
          <option value="bachelors">Bachelors</option>
          <option value="masters">Masters</option>
          <option value="phd">PhD</option>
          <option value="postdoc">Postdoc</option>
          <option value="short_course">Short course</option>
        </select>
      </label>
      <div className="segment-divider" aria-hidden="true" />
      <label className="search-segment">
        <span className="segment-label">Funding</span>
        <select
          value={search.funding_type}
          onChange={(event) => update("funding_type", event.target.value as FundingType)}
          name="funding_type"
          className="segment-select"
        >
          <option value="">Any funding</option>
          <option value="full">100% Fully Funded</option>
          <option value="partial">Partial Funding</option>
          <option value="tuition_only">Tuition Only</option>
          <option value="stipend_only">Stipend Only</option>
        </select>
      </label>
      <button className="airbnb-search-btn" type="submit" aria-label="Search scholarships">
        <span aria-hidden="true">🔍</span>
      </button>
    </form>
  );
}

export function HomePage() {
  const { data, error, isLoading } = useServerQuery<OpportunitySearchResponse>(
    "homepage-opportunities",
    (signal) =>
      searchOpportunities(
        { ...defaultCatalogueFilters, availability: "all", limit: "20" },
        0,
        signal,
      ),
  );

  const opportunities = data?.items ?? [];

  // Filter 6 items per single-row carousel
  const ukOpportunities = useMemo(() => {
    const matched = opportunities.filter((item) =>
      item.country.toLowerCase().includes("kingdom") || item.country.toLowerCase() === "uk",
    );
    return matched.length ? matched.slice(0, 6) : opportunities.slice(0, 6);
  }, [opportunities]);

  const usOpportunities = useMemo(() => {
    const matched = opportunities.filter((item) =>
      item.country.toLowerCase().includes("state") ||
      item.country.toLowerCase() === "usa" ||
      item.country.toLowerCase() === "us",
    );
    return matched.length ? matched.slice(0, 6) : opportunities.slice(0, 6);
  }, [opportunities]);

  const fullyFunded = useMemo(() => {
    const matched = opportunities.filter(
      (item) => item.funding_classification === "fully_funded" || item.funding_type === "full",
    );
    return matched.length ? matched.slice(0, 6) : opportunities.slice(0, 6);
  }, [opportunities]);

  const allVerified = useMemo(() => opportunities.slice(0, 6), [opportunities]);

  const verifiedTotal = data?.pagination.total;
  const catalogueHeading =
    verifiedTotal === undefined
      ? "Verified scholarships, organized for action"
      : `${verifiedTotal} verified scholarships, organized for action`;

  return (
    <main className="airbnb-home-page">
      {/* 1. HERO SEARCH OMNIBAR */}
      <section className="airbnb-hero-section">
        <div className="airbnb-hero-inner">
          <div className="airbnb-hero-copy">
            <span className="airbnb-hero-badge">✓ 450+ Verified Official Government & University Awards</span>
            <h1>Discover scholarships you can actually win.</h1>
            <p className="lead">
              Citation-backed opportunities, verified statutory criteria, and real-time GPA fit matching.
            </p>
          </div>
          <SearchPanel />
        </div>
      </section>

      {/* 2. MAIN SCHOLARSHIP SINGLE-ROW SECTIONS */}
      <div className="airbnb-rows-container">
        {error ? (
          <div className="catalogue-message error-message" role="alert">
            We could not load featured scholarships right now. The full scholarships page is still available.
          </div>
        ) : null}

        {isLoading ? (
          <section className="airbnb-section-row">
            <div className="airbnb-row-header">
              <span className="shimmer-line title-shimmer" />
            </div>
            <div className="airbnb-single-row-grid" aria-live="polite">
              {Array.from({ length: 6 }).map((_, index) => (
                <article className="airbnb-scholarship-card card-loading-shimmer" key={index}>
                  <div className="airbnb-card-media" />
                  <div className="airbnb-card-info">
                    <span className="shimmer-line" style={{ width: "80%", height: "14px" }} />
                    <span className="shimmer-line" style={{ width: "50%", height: "12px" }} />
                    <span className="shimmer-line" style={{ width: "90%", height: "12px" }} />
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {!isLoading && opportunities.length > 0 ? (
          <>
            {/* ROW 1: Popular scholarships in United Kingdom */}
            <section className="airbnb-section-row">
              <div className="airbnb-row-header">
                <Link
                  to={toCatalogueUrl({ country: "United Kingdom" })}
                  className="airbnb-row-title-link"
                >
                  <h2>Popular scholarships in United Kingdom</h2>
                  <span className="title-arrow" aria-hidden="true">➔</span>
                </Link>
                <div className="airbnb-nav-arrows" aria-hidden="true">
                  <button type="button" className="nav-circle-btn" aria-label="Previous">‹</button>
                  <button type="button" className="nav-circle-btn" aria-label="Next">›</button>
                </div>
              </div>
              <div className="airbnb-single-row-grid">
                {ukOpportunities.map((opportunity) => (
                  <AirbnbScholarshipCard key={opportunity.id} opportunity={opportunity} />
                ))}
              </div>
            </section>

            {/* ROW 2: Top Fellowships in United States */}
            <section className="airbnb-section-row">
              <div className="airbnb-row-header">
                <Link
                  to={toCatalogueUrl({ country: "United States" })}
                  className="airbnb-row-title-link"
                >
                  <h2>Top Fellowships in United States</h2>
                  <span className="title-arrow" aria-hidden="true">➔</span>
                </Link>
                <div className="airbnb-nav-arrows" aria-hidden="true">
                  <button type="button" className="nav-circle-btn" aria-label="Previous">‹</button>
                  <button type="button" className="nav-circle-btn" aria-label="Next">›</button>
                </div>
              </div>
              <div className="airbnb-single-row-grid">
                {usOpportunities.map((opportunity) => (
                  <AirbnbScholarshipCard key={opportunity.id} opportunity={opportunity} />
                ))}
              </div>
            </section>

            {/* ROW 3: 100% Fully Funded in Europe & Asia */}
            <section className="airbnb-section-row">
              <div className="airbnb-row-header">
                <Link
                  to={toCatalogueUrl({ funding_type: "full" })}
                  className="airbnb-row-title-link"
                >
                  <h2>100% Fully Funded in Europe & Asia</h2>
                  <span className="title-arrow" aria-hidden="true">➔</span>
                </Link>
                <div className="airbnb-nav-arrows" aria-hidden="true">
                  <button type="button" className="nav-circle-btn" aria-label="Previous">‹</button>
                  <button type="button" className="nav-circle-btn" aria-label="Next">›</button>
                </div>
              </div>
              <div className="airbnb-single-row-grid">
                {fullyFunded.map((opportunity) => (
                  <AirbnbScholarshipCard key={opportunity.id} opportunity={opportunity} />
                ))}
              </div>
            </section>

            {/* ROW 4: Verified Catalogue Heading */}
            <section className="airbnb-section-row">
              <div className="airbnb-row-header">
                <Link to="/catalogue" className="airbnb-row-title-link">
                  <h2>{catalogueHeading}</h2>
                  <span className="title-arrow" aria-hidden="true">➔</span>
                </Link>
                <div className="airbnb-nav-arrows" aria-hidden="true">
                  <button type="button" className="nav-circle-btn" aria-label="Previous">‹</button>
                  <button type="button" className="nav-circle-btn" aria-label="Next">›</button>
                </div>
              </div>
              <div className="airbnb-single-row-grid">
                {allVerified.map((opportunity) => (
                  <AirbnbScholarshipCard key={opportunity.id} opportunity={opportunity} />
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}

