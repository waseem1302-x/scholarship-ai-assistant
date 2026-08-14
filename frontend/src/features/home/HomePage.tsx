import { type FormEvent, useMemo, useState } from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import {
  catalogueSearch,
  deadlineLabel,
  formatDate,
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

const categoryLinks = [
  { label: "Open now", search: { availability: "open" as const } },
  { label: "Fully funded", search: { funding_type: "full" as const } },
  { label: "Bachelors", search: { degree_level: "bachelors" as const } },
  { label: "Masters", search: { degree_level: "masters" as const } },
  { label: "PhD", search: { degree_level: "phd" as const } },
  { label: "Europe", search: { country: "United Kingdom" } },
  { label: "Asia", search: { country: "Malaysia" } },
  { label: "No IELTS", search: { field: "English flexible" } },
  { label: "Government", search: { field: "Government" } },
];

const spotlightCountries = [
  { label: "United Kingdom", hint: "Chevening, Commonwealth, university awards" },
  { label: "United States", hint: "Fulbright, institutional aid, fellowships" },
  { label: "Canada", hint: "Graduate funding and research scholarships" },
  { label: "Australia", hint: "Government and university funding" },
  { label: "Malaysia", hint: "Regional and university opportunities" },
];

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
  if (normalized.includes("state") || normalized === "usa") return "usa";
  if (normalized.includes("canada")) return "canada";
  if (normalized.includes("australia")) return "australia";
  if (normalized.includes("malaysia")) return "malaysia";
  if (normalized.includes("germany") || normalized.includes("france") || normalized.includes("europe")) return "europe";
  return "global";
}

function statusLabel(opportunity: OpportunitySummary): string {
  if (opportunity.application_window_state === "open") return "Open now";
  if (opportunity.application_window_state === "upcoming") return "Upcoming";
  if (opportunity.application_window_state === "rolling") return "Rolling";
  return deadlineLabel(opportunity.application_deadline);
}

function ScholarshipCard({ opportunity }: { opportunity: OpportunitySummary }) {
  return (
    <article className="home-opportunity-card">
      <div className={`scholarship-visual scholarship-visual-${visualTone(opportunity.country)}`} aria-hidden="true">
        <span>{opportunity.country}</span>
      </div>
      <div className="home-card-body">
        <div className="home-card-meta">
          <span>{statusLabel(opportunity)}</span>
          <span>{opportunity.verification_freshness === "recent" ? "Verified" : "Official source"}</span>
        </div>
        <h3>{opportunity.name}</h3>
        <p>{opportunity.provider_name}</p>
        <div className="home-card-tags" aria-label="Scholarship summary">
          <span>{opportunity.country}</span>
          <span>{readableValue(opportunity.degree_level)}</span>
          <span>{opportunity.funding_display_label}</span>
        </div>
        <p className="home-card-funding">{opportunity.funding_summary}</p>
        <div className="home-card-actions">
          <Link className="button button-primary" to={`/catalogue/${opportunity.id}`}>
            Check my fit
          </Link>
          <span>Source checked {formatDate(opportunity.last_verified_at)}</span>
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
    <form className="home-search-panel" onSubmit={submit} aria-label="Search verified scholarships">
      <label>
        <span>Where</span>
        <input
          value={search.country}
          onChange={(event) => update("country", event.target.value)}
          placeholder="Country or region"
          name="country"
        />
      </label>
      <label>
        <span>Level</span>
        <select
          value={search.degree_level}
          onChange={(event) => update("degree_level", event.target.value)}
          name="degree_level"
        >
          <option value="">Any degree</option>
          <option value="bachelors">Bachelors</option>
          <option value="masters">Masters</option>
          <option value="phd">PhD</option>
          <option value="postdoc">Postdoc</option>
          <option value="short_course">Short course</option>
        </select>
      </label>
      <label>
        <span>Field</span>
        <input
          value={search.field}
          onChange={(event) => update("field", event.target.value)}
          placeholder="Computer science, health..."
          name="field"
        />
      </label>
      <label>
        <span>Funding</span>
        <select
          value={search.funding_type}
          onChange={(event) => update("funding_type", event.target.value)}
          name="funding_type"
        >
          <option value="">Any funding</option>
          <option value="full">Full funding</option>
          <option value="partial">Partial funding</option>
          <option value="tuition_only">Tuition only</option>
          <option value="stipend_only">Stipend only</option>
        </select>
      </label>
      <button className="home-search-button" type="submit" aria-label="Search scholarships">
        Search
      </button>
    </form>
  );
}

export function HomePage() {
  const { user, isRestoring } = useAuth();
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
  const openOrPriority = useMemo(
    () =>
      opportunities
        .filter((item) => item.application_window_state !== "closed")
        .slice(0, 6),
    [opportunities],
  );
  const fullyFunded = useMemo(
    () =>
      opportunities
        .filter((item) => item.funding_classification === "fully_funded" || item.funding_type === "full")
        .slice(0, 4),
    [opportunities],
  );
  const displayItems = openOrPriority.length ? openOrPriority : opportunities.slice(0, 6);
  const verifiedTotal = data?.pagination.total ?? 500;

  return (
    <main className="home-page">
      <section className="home-hero">
        <div className="page-width home-hero-inner">
          <div className="home-hero-copy">
            <p className="eyebrow">Scholarship discovery, built like a decision system</p>
            <h1>Find scholarships you can actually act on.</h1>
            <p className="lead">
              Search verified opportunities, understand the source evidence, and turn a confusing
              scholarship hunt into a focused application plan.
            </p>
          </div>
          <SearchPanel />
          <div className="home-category-rail" aria-label="Popular scholarship paths">
            {categoryLinks.map((category) => (
              <NavLink key={category.label} to={toCatalogueUrl(category.search)}>
                <span aria-hidden="true" />
                {category.label}
              </NavLink>
            ))}
          </div>
        </div>
      </section>

      <section className="home-country-band">
        <div className="page-width">
          <div className="home-section-heading">
            <div>
              <p className="eyebrow">Explore by destination</p>
              <h2>Country context without turning scholarships into travel ads</h2>
            </div>
          </div>
          <div className="home-country-grid">
            {spotlightCountries.map((country) => (
              <NavLink
                className={`home-country-card scholarship-visual-${visualTone(country.label)}`}
                key={country.label}
                to={toCatalogueUrl({ country: country.label })}
              >
                <span>{country.label}</span>
                <strong>{country.hint}</strong>
              </NavLink>
            ))}
          </div>
        </div>
      </section>

      <section className="page-width home-market">
        <div className="home-section-heading">
          <div>
              <p className="eyebrow">Verified scholarships</p>
              <h2>{verifiedTotal}+ scholarships, organized for action</h2>
          </div>
          <NavLink className="button button-quiet" to="/catalogue">
            Browse all
          </NavLink>
        </div>

        <div className="home-stats-row" aria-label="Platform strengths">
          <article>
            <strong>Official</strong>
            <span>Every public record links back to its source.</span>
          </article>
          <article>
            <strong>Specific</strong>
            <span>Funding, deadlines, country, level, and eligibility stay visible.</span>
          </article>
          <article>
            <strong>Personal</strong>
            <span>Your workspace turns discovery into next actions.</span>
          </article>
        </div>

        {error ? (
          <div className="catalogue-message error-message" role="alert">
            We could not load featured scholarships right now. The full scholarships page is still available.
          </div>
        ) : null}

        {isLoading ? (
          <div className="home-card-grid" aria-live="polite">
            {Array.from({ length: 6 }).map((_, index) => (
              <article className="home-opportunity-card home-card-loading" key={index}>
                <div className="scholarship-visual scholarship-visual-global" />
                <div className="home-card-body">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {!isLoading && displayItems.length ? (
          <div className="home-card-grid">
            {displayItems.map((opportunity) => (
              <ScholarshipCard key={opportunity.id} opportunity={opportunity} />
            ))}
          </div>
        ) : null}
      </section>

      <section className="page-width home-ai-strip">
        <div>
          <p className="eyebrow">Scholarship AI, not general chat</p>
          <h2>Ask for fit, missing documents, comparison, and next steps.</h2>
          <p>
            The assistant is strongest when it works from verified scholarship records and your
            structured profile, so advice stays tied to real requirements instead of generic answers.
          </p>
        </div>
        <div className="home-ai-actions">
          <NavLink className="button button-primary" to={user ? "/assistant" : "/auth"}>
            {isRestoring ? "Preparing..." : user ? "Open assistant" : "Create workspace"}
          </NavLink>
          <NavLink className="button button-quiet" to={user ? "/dashboard" : "/catalogue"}>
            {user ? "Open workspace" : "Browse first"}
          </NavLink>
        </div>
      </section>

      {!isLoading && fullyFunded.length ? (
        <section className="page-width home-market home-market-compact">
          <div className="home-section-heading">
            <div>
              <p className="eyebrow">High-value paths</p>
              <h2>Fully funded opportunities to review first</h2>
            </div>
            <NavLink className="button button-quiet" to={toCatalogueUrl({ funding_type: "full" })}>
              See fully funded
            </NavLink>
          </div>
          <div className="home-card-grid home-card-grid-compact">
            {fullyFunded.map((opportunity) => (
              <ScholarshipCard key={opportunity.id} opportunity={opportunity} />
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
