import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useServerQuery } from "../../hooks/useServerQuery";
import {
  catalogueSearch,
  deadlineLabel,
  getCountryFlag,
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

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface HomeSearchState {
  country: string;
  degree_level: DegreeLevel | "";
  funding_type: FundingType | "";
}

type ActivePopover = "where" | "degree" | "funding" | null;

/* ------------------------------------------------------------------ */
/*  Static Data                                                        */
/* ------------------------------------------------------------------ */

const initialSearch: HomeSearchState = {
  country: "",
  degree_level: "",
  funding_type: "",
};

const categoryLinks = [
  { label: "All", icon: "🌐", search: {} },
  { label: "Fully funded", icon: "🏆", search: { funding_type: "full" as const } },
  { label: "Bachelor", icon: "🎓", search: { degree_level: "bachelors" as const } },
  { label: "Masters", icon: "📚", search: { degree_level: "masters" as const } },
  { label: "PhD", icon: "🔬", search: { degree_level: "phd" as const } },
  { label: "Asia", icon: "🌏", search: { country: "Malaysia" } },
  { label: "Europe", icon: "🏛️", search: { country: "Europe" } },
  { label: "UK", icon: "🇬🇧", search: { country: "United Kingdom" } },
  { label: "USA", icon: "🇺🇸", search: { country: "United States" } },
  { label: "No IELTS", icon: "⚡", search: { field: "English flexible" } },
];

const popularDestinations = [
  { country: "United Kingdom", flag: "🇬🇧", hint: "Chevening, Oxford, Cambridge" },
  { country: "United States", flag: "🇺🇸", hint: "Fulbright, Harvard, MIT" },
  { country: "Germany", flag: "🇩🇪", hint: "DAAD, Free tuition public universities" },
  { country: "Canada", flag: "🇨🇦", hint: "Vanier, Toronto, McGill" },
  { country: "Australia", flag: "🇦🇺", hint: "Australia Awards, Melbourne" },
  { country: "Japan", flag: "🇯🇵", hint: "MEXT Government, Tokyo, Kyoto" },
  { country: "Malaysia", flag: "🇲🇾", hint: "MIS Government, UM, UTM" },
  { country: "Singapore", flag: "🇸🇬", hint: "NUS, NTU, A*STAR Fellowships" },
  { country: "Europe", flag: "🇪🇺", hint: "Erasmus Mundus Joint Masters" },
];

const degreeOptions: { label: string; value: DegreeLevel | ""; icon: string; desc: string }[] = [
  { label: "Any degree", value: "", icon: "🌐", desc: "All academic degree levels" },
  { label: "Bachelors", value: "bachelors", icon: "🎓", desc: "Undergraduate & freshman grants" },
  { label: "Masters", value: "masters", icon: "📚", desc: "Postgraduate & professional degrees" },
  { label: "PhD / Doctorate", value: "phd", icon: "🔬", desc: "Research fellowships & doctorates" },
  { label: "Postdoc", value: "postdoc", icon: "🧪", desc: "Postdoctoral scientific research" },
  { label: "Short course", value: "short_course", icon: "⚡", desc: "Summer schools & training" },
];

const fundingOptions: { label: string; value: FundingType | ""; icon: string; desc: string }[] = [
  { label: "Any funding", value: "", icon: "💎", desc: "All funding coverage types" },
  { label: "100% Full Funding", value: "full", icon: "🏆", desc: "Tuition + monthly living stipend + flights" },
  { label: "Partial Aid", value: "partial", icon: "💵", desc: "Tuition discount or partial stipend" },
  { label: "Tuition Only", value: "tuition_only", icon: "🏛️", desc: "100% tuition waiver coverage" },
  { label: "Stipend Only", value: "stipend_only", icon: "💳", desc: "Monthly living allowance grant" },
];

const spotlightCountries = [
  { label: "United Kingdom", hint: "Chevening, Commonwealth, university awards", count: "148" },
  { label: "United States", hint: "Fulbright, institutional aid, fellowships", count: "210" },
  { label: "Germany", hint: "DAAD, tuition-free public universities", count: "84" },
  { label: "Canada", hint: "Vanier, Banting, Trillium scholarships", count: "92" },
  { label: "Australia", hint: "Government and university funding", count: "65" },
];

const discoveryFooterGroups = [
  {
    title: "Popular",
    links: [
      { label: "Scholarships in Asia", hint: "Japan, Korea, Malaysia", search: { country: "Malaysia" } },
      { label: "Scholarships in Europe", hint: "Germany, UK, France", search: { country: "Europe" } },
      { label: "Government awards", hint: "Official national funding", search: { field: "Government" } },
      { label: "No IELTS routes", hint: "English-flexible options", search: { field: "English flexible" } },
    ],
  },
  {
    title: "Degree",
    links: [
      { label: "Fully funded bachelor", hint: "Undergraduate awards", search: { degree_level: "bachelors" as const, funding_type: "full" as const } },
      { label: "Masters scholarships", hint: "Coursework and research", search: { degree_level: "masters" as const } },
      { label: "PhD fellowships", hint: "Research funding", search: { degree_level: "phd" as const } },
      { label: "Short courses", hint: "Exchange and training", search: { degree_level: "short_course" as const } },
    ],
  },
  {
    title: "Workspace",
    links: [
      { label: "Build your profile", hint: "Match-ready student passport", to: "/profile" },
      { label: "Explainable matches", hint: "Evidence-linked eligibility", to: "/matches" },
      { label: "Application tracker", hint: "Tasks and deadlines", to: "/applications" },
      { label: "Verified catalogue", hint: "Browse every record", to: "/catalogue" },
    ],
  },
];

const asiaCountries = [
  "brunei",
  "china",
  "hong kong",
  "india",
  "indonesia",
  "japan",
  "korea",
  "malaysia",
  "pakistan",
  "singapore",
  "taiwan",
  "thailand",
  "turkey",
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function toCatalogueUrl(partial: Partial<typeof defaultCatalogueFilters>): string {
  const filters = {
    ...defaultCatalogueFilters,
    availability: "all" as const,
    limit: "20" as const,
    ...partial,
  };
  return "/catalogue?" + catalogueSearch(filters, 0).toString();
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

function windowLabel(opportunity: OpportunitySummary): { text: string; tone: "open" | "upcoming" | "rolling" | "neutral" } {
  if (opportunity.application_window_state === "open") return { text: "Open now", tone: "open" };
  if (opportunity.application_window_state === "upcoming") return { text: "Upcoming", tone: "upcoming" };
  if (opportunity.application_window_state === "rolling") return { text: "Rolling", tone: "rolling" };
  return { text: deadlineLabel(opportunity.application_deadline), tone: "neutral" };
}

function fundingBadge(opportunity: OpportunitySummary): string | null {
  if (opportunity.funding_classification === "fully_funded" || opportunity.funding_type === "full") return "Guest favorite";
  if (opportunity.funding_type === "partial") return "Partial Aid";
  return "Top Choice";
}

function hasDegree(opportunity: OpportunitySummary, degree: DegreeLevel): boolean {
  return opportunity.degree_level === degree || Boolean(opportunity.degree_levels?.includes(degree));
}

function isFullyFunded(opportunity: OpportunitySummary): boolean {
  return opportunity.funding_classification === "fully_funded" || opportunity.funding_type === "full";
}

function isAsiaOpportunity(opportunity: OpportunitySummary): boolean {
  const country = opportunity.country.toLowerCase();
  return asiaCountries.some((keyword) => country.includes(keyword));
}

function scholarshipSignal(opportunity: OpportunitySummary): string {
  if (opportunity.catalogue_decision_tier === "decision_ready") return "Decision-ready";
  if (opportunity.structured_eligibility_complete) return "Eligibility mapped";
  return "Source-backed";
}

/* ------------------------------------------------------------------ */
/*  Shelf Scroll Helpers                                               */
/* ------------------------------------------------------------------ */

function scrollShelf(ref: React.RefObject<HTMLDivElement | null>, direction: "left" | "right") {
  if (!ref.current) return;
  const scrollAmount = ref.current.clientWidth * 0.75;
  ref.current.scrollBy({ left: direction === "left" ? -scrollAmount : scrollAmount, behavior: "smooth" });
}

/* ------------------------------------------------------------------ */
/*  Sub-Components                                                     */
/* ------------------------------------------------------------------ */

function SearchPill() {
  const navigate = useNavigate();
  const [search, setSearch] = useState<HomeSearchState>(initialSearch);
  const [activePopover, setActivePopover] = useState<ActivePopover>(null);
  const pillRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (pillRef.current && !pillRef.current.contains(event.target as Node)) {
        setActivePopover(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function update(key: keyof HomeSearchState, value: string) {
    setSearch((current) => ({ ...current, [key]: value }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActivePopover(null);
    navigate(toCatalogueUrl(search));
  }

  function selectDestination(country: string) {
    update("country", country);
    setActivePopover("degree");
  }

  function selectDegree(level: DegreeLevel | "") {
    update("degree_level", level);
    setActivePopover("funding");
  }

  function selectFunding(funding: FundingType | "") {
    update("funding_type", funding);
    setActivePopover(null);
  }

  return (
    <div className="home-search-pill-wrapper" ref={pillRef}>
      <form
        className={"home-search-pill " + (activePopover ? "home-search-pill--active" : "")}
        onSubmit={submit}
        aria-label="Search verified scholarships"
      >
        {/* Where Segment */}
        <div
          className={"home-search-pill__segment " + (activePopover === "where" ? "home-search-pill__segment--selected" : "")}
          onClick={() => setActivePopover((curr) => (curr === "where" ? null : "where"))}
        >
          <span className="home-search-pill__label">Where</span>
          <input
            value={search.country}
            onChange={(event) => update("country", event.target.value)}
            placeholder="Search countries or scholarships"
            name="country"
            className="home-search-pill__input"
            onFocus={() => setActivePopover("where")}
            autoComplete="off"
          />
        </div>

        <div className="home-search-pill__divider" />

        {/* Degree Level Segment */}
        <div
          className={"home-search-pill__segment " + (activePopover === "degree" ? "home-search-pill__segment--selected" : "")}
          onClick={() => setActivePopover((curr) => (curr === "degree" ? null : "degree"))}
        >
          <span className="home-search-pill__label">Degree</span>
          <div className="home-search-pill__input">
            {search.degree_level ? readableValue(search.degree_level) : <span style={{ color: "var(--airbnb-muted)", fontWeight: 400 }}>Any degree</span>}
          </div>
        </div>

        <div className="home-search-pill__divider" />

        {/* Funding Segment */}
        <div
          className={"home-search-pill__segment " + (activePopover === "funding" ? "home-search-pill__segment--selected" : "")}
          onClick={() => setActivePopover((curr) => (curr === "funding" ? null : "funding"))}
        >
          <span className="home-search-pill__label">Funding</span>
          <div className="home-search-pill__input">
            {search.funding_type === "full"
              ? "100% Full Funding"
              : search.funding_type
              ? readableValue(search.funding_type)
              : <span style={{ color: "var(--airbnb-muted)", fontWeight: 400 }}>Any funding</span>}
          </div>
        </div>

        {/* Search Action Button */}
        <button className="home-search-pill__button" type="submit" aria-label="Search scholarships">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </button>
      </form>

      {/* Popovers */}
      {activePopover === "where" && (
        <div className="home-search-popover home-search-popover--where" role="dialog" aria-label="Choose destination">
          <h4>Popular study destinations</h4>
          <div className="home-search-popover__grid">
            {popularDestinations.map((dest) => (
              <button
                key={dest.country}
                type="button"
                className={"home-search-popover__chip " + (search.country === dest.country ? "active" : "")}
                onClick={() => selectDestination(dest.country)}
              >
                <span className="home-search-popover__chip-flag">{dest.flag}</span>
                <span className="home-search-popover__chip-title">{dest.country}</span>
                <span className="home-search-popover__chip-sub">{dest.hint}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {activePopover === "degree" && (
        <div className="home-search-popover home-search-popover--degree" role="dialog" aria-label="Choose degree level">
          <h4>Select degree level</h4>
          <div className="home-search-popover__list">
            {degreeOptions.map((opt) => (
              <div
                key={opt.label}
                className={"home-search-popover__item " + (search.degree_level === opt.value ? "active" : "")}
                onClick={() => selectDegree(opt.value)}
              >
                <div>
                  <div className="home-search-popover__item-title">{opt.label}</div>
                  <small style={{ color: "var(--airbnb-muted)", fontSize: "0.76rem" }}>{opt.desc}</small>
                </div>
                <span className="home-search-popover__item-icon">{opt.icon}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {activePopover === "funding" && (
        <div className="home-search-popover home-search-popover--funding" role="dialog" aria-label="Choose funding coverage">
          <h4>Select funding coverage</h4>
          <div className="home-search-popover__list">
            {fundingOptions.map((opt) => (
              <div
                key={opt.label}
                className={"home-search-popover__item " + (search.funding_type === opt.value ? "active" : "")}
                onClick={() => selectFunding(opt.value)}
              >
                <div>
                  <div className="home-search-popover__item-title">{opt.label}</div>
                  <small style={{ color: "var(--airbnb-muted)", fontSize: "0.76rem" }}>{opt.desc}</small>
                </div>
                <span className="home-search-popover__item-icon">{opt.icon}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CategoryRibbon({ activeIndex, onSelect }: { activeIndex: number; onSelect: (index: number) => void }) {
  return (
    <div className="home-category-ribbon">
      <div className="home-category-ribbon__track" role="tablist" aria-label="Scholarship categories">
        {categoryLinks.map((category, index) => (
          <NavLink
            key={category.label}
            to={toCatalogueUrl(category.search)}
            className={"home-category-ribbon__item " + (index === activeIndex ? "home-category-ribbon__item--active" : "")}
            role="tab"
            aria-selected={index === activeIndex}
            onClick={(event) => {
              event.preventDefault();
              onSelect(index);
            }}
          >
            <span className="home-category-ribbon__icon" aria-hidden="true">{category.icon}</span>
            <span className="home-category-ribbon__text">{category.label}</span>
          </NavLink>
        ))}
      </div>
      <div className="home-category-ribbon__controls">
        <NavLink className="home-category-ribbon__filter-btn" to="/catalogue">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" />
            <line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" />
            <line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" />
            <line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" />
            <line x1="17" y1="16" x2="23" y2="16" />
          </svg>
          Filters
        </NavLink>
      </div>
    </div>
  );
}

function ScholarshipCard({ opportunity }: { opportunity: OpportunitySummary }) {
  const [saved, setSaved] = useState(false);

  const badge = fundingBadge(opportunity);
  const window = windowLabel(opportunity);
  const flag = getCountryFlag(opportunity.country);

  function toggleSave(event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    setSaved((prev) => !prev);
  }

  return (
    <Link className="home-card" to={"/catalogue/" + opportunity.id}>
      {/* Visual / Image area with Airbnb card style */}
      <div className={"home-card__visual scholarship-visual-" + visualTone(opportunity.country)}>
        {badge ? (
          <span className="home-card__badge">{badge}</span>
        ) : null}
        <button
          className={"home-card__heart " + (saved ? "home-card__heart--saved" : "")}
          type="button"
          aria-label={saved ? "Remove from saved" : "Save scholarship"}
          onClick={toggleSave}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill={saved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
            <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
          </svg>
        </button>
        <div className="home-card__visual-art" aria-hidden="true">
          <span className="home-card__seal">{flag}</span>
          <span className="home-card__document" />
          <span className="home-card__ribbon" />
        </div>
        <div className="home-card__dots" aria-hidden="true">
          <span className="home-card__dot home-card__dot--active" />
          <span className="home-card__dot" />
          <span className="home-card__dot" />
        </div>
        <span className="home-card__country-label" aria-hidden="true">{opportunity.country}</span>
      </div>

      {/* Strict Airbnb Typography Hierarchy */}
      <div className="home-card__meta">
        <div className="home-card__row-top">
          <span className="home-card__location">{flag} {opportunity.country}</span>
          <span className="home-card__verified" title="Officially verified scholarship source">
            ★ {opportunity.verification_freshness === "recent" ? "4.98" : "4.92"}
          </span>
        </div>
        <h3 className="home-card__title">{opportunity.name}</h3>
        <p className="home-card__subtitle">{opportunity.provider_name} · {readableValue(opportunity.degree_level)}</p>
        <p className={"home-card__deadline home-card__deadline--" + window.tone}>{window.text}</p>
        <p className="home-card__price">
          <strong>{opportunity.funding_display_label}</strong>
          <span> · {scholarshipSignal(opportunity)}</span>
        </p>
      </div>
    </Link>
  );
}

function ShelfRow({
  title,
  browseUrl,
  items,
  isLoading,
}: {
  title: string;
  browseUrl: string;
  items: OpportunitySummary[];
  isLoading?: boolean;
}) {
  const railRef = useRef<HTMLDivElement>(null);

  return (
    <section className="home-shelf">
      <div className="home-shelf__header">
        <NavLink className="home-shelf__title" to={browseUrl}>
          {title}
          <span aria-hidden="true"> →</span>
        </NavLink>
        <div className="home-shelf__arrows">
          <button
            className="home-shelf__arrow"
            type="button"
            aria-label="Scroll left"
            onClick={() => scrollShelf(railRef, "left")}
          >
            ‹
          </button>
          <button
            className="home-shelf__arrow"
            type="button"
            aria-label="Scroll right"
            onClick={() => scrollShelf(railRef, "right")}
          >
            ›
          </button>
        </div>
      </div>

      <div className="home-shelf__rail" ref={railRef}>
        {isLoading
          ? Array.from({ length: 7 }).map((_, index) => (
              <article className="home-card home-card--loading" key={index}>
                <div className="home-card__visual scholarship-visual-global" />
                <div className="home-card__meta">
                  <span /><span /><span />
                </div>
              </article>
            ))
          : items.map((opportunity) => (
              <ScholarshipCard key={opportunity.id} opportunity={opportunity} />
            ))}
      </div>
    </section>
  );
}

function DiscoveryFooter() {
  return (
    <section className="home-discovery-footer" aria-labelledby="home-discovery-title">
      <h2 id="home-discovery-title">Inspiration for future applications</h2>
      <div className="home-discovery-footer__grid">
        {discoveryFooterGroups.map((group) => (
          <div className="home-discovery-footer__group" key={group.title}>
            <h3>{group.title}</h3>
            <div className="home-discovery-footer__links">
              {group.links.map((link) => {
                const to = "to" in link ? link.to : toCatalogueUrl(link.search);
                return (
                  <NavLink className="home-discovery-footer__link" key={link.label} to={to}>
                    <span>{link.label}</span>
                    <small>{link.hint}</small>
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export function HomePage() {
  const { user, isRestoring } = useAuth();
  const [activeCategory, setActiveCategory] = useState(0);
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
  const verifiedTotal = data?.pagination.total ?? 0;

  const openOrPriority = useMemo(
    () =>
      opportunities
        .filter((item) => item.application_window_state !== "closed")
        .slice(0, 8),
    [opportunities],
  );

  const fullyFunded = useMemo(
    () =>
      opportunities
        .filter(isFullyFunded)
        .slice(0, 8),
    [opportunities],
  );

  const fullyFundedBachelor = useMemo(
    () =>
      opportunities
        .filter((item) => isFullyFunded(item) && hasDegree(item, "bachelors"))
        .slice(0, 8),
    [opportunities],
  );

  const fullyFundedAsia = useMemo(
    () =>
      opportunities
        .filter((item) => isFullyFunded(item) && isAsiaOpportunity(item))
        .slice(0, 8),
    [opportunities],
  );

  const ukEuropeOpportunities = useMemo(
    () =>
      opportunities
        .filter((item) => {
          const c = item.country.toLowerCase();
          return c.includes("kingdom") || c.includes("germany") || c.includes("france") || c.includes("europe");
        })
        .slice(0, 8),
    [opportunities],
  );

  const remaining = useMemo(
    () => opportunities.slice(0, 8),
    [opportunities],
  );

  const displayShelfTitle = verifiedTotal
    ? verifiedTotal + " verified scholarships"
    : null;

  return (
    <main className="home-page">
      {/* -------- Search Pill -------- */}
      <section className="home-hero">
        <div className="page-width">
          <SearchPill />
        </div>
      </section>

      {/* -------- Category Ribbon -------- */}
      <section className="home-ribbon-bar">
        <div className="page-width">
          <CategoryRibbon activeIndex={activeCategory} onSelect={setActiveCategory} />
        </div>
      </section>

      {/* -------- Curated Shelf Rows -------- */}
      <div className="page-width home-feed">
        {error ? (
          <div className="catalogue-message error-message" role="alert">
            We could not load featured scholarships right now. The full catalogue is still available.
          </div>
        ) : null}

        {/* Shelf 1: Open or priority */}
        {displayShelfTitle ? (
          <ShelfRow
            title={"Currently open scholarships · " + displayShelfTitle}
            browseUrl="/catalogue"
            items={openOrPriority.length ? openOrPriority : remaining}
            isLoading={isLoading}
          />
        ) : isLoading ? (
          <ShelfRow
            title="Loading scholarships…"
            browseUrl="/catalogue"
            items={[]}
            isLoading
          />
        ) : null}

        {/* Shelf 2: Fully funded */}
        {!isLoading && fullyFunded.length ? (
          <ShelfRow
            title="Fully funded scholarships"
            browseUrl={toCatalogueUrl({ funding_type: "full" })}
            items={fullyFunded}
          />
        ) : null}

        {/* Shelf 3: Fully funded bachelor */}
        {!isLoading && fullyFundedBachelor.length ? (
          <ShelfRow
            title="Fully funded bachelor"
            browseUrl={toCatalogueUrl({ degree_level: "bachelors", funding_type: "full" })}
            items={fullyFundedBachelor}
          />
        ) : null}

        {/* Shelf 4: Fully funded in Asia */}
        {!isLoading && fullyFundedAsia.length ? (
          <ShelfRow
            title="Fully funded in Asia"
            browseUrl={toCatalogueUrl({ country: "Malaysia", funding_type: "full" })}
            items={fullyFundedAsia}
          />
        ) : null}

        {/* Shelf 5: UK & Europe Awards */}
        {!isLoading && ukEuropeOpportunities.length ? (
          <ShelfRow
            title="Top awards in United Kingdom & Europe"
            browseUrl={toCatalogueUrl({ country: "United Kingdom" })}
            items={ukEuropeOpportunities}
          />
        ) : null}

        {/* -------- Country Destinations -------- */}
        <section className="home-country-band">
          <div className="home-shelf__header">
            <h2 className="home-shelf__title home-shelf__title--static">
              Explore by study abroad destination
            </h2>
          </div>
          <div className="home-country-grid">
            {spotlightCountries.map((country) => (
              <NavLink
                className={"home-country-card scholarship-visual-" + visualTone(country.label)}
                key={country.label}
                to={toCatalogueUrl({ country: country.label })}
              >
                <span className="home-country-card__flag">{getCountryFlag(country.label)}</span>
                <span className="home-country-card__name">{country.label}</span>
                <strong className="home-country-card__hint">{country.hint}</strong>
              </NavLink>
            ))}
          </div>
        </section>

        {/* -------- AI Strip -------- */}
        <section className="home-ai-strip">
          <div>
            <p className="eyebrow">Scholarship AI, not general chat</p>
            <h2>Not sure which scholarships you qualify for?</h2>
            <p>
              The assistant analyzes official grant criteria from verified scholarship records
              and your structured profile, so advice stays tied to real requirements.
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

        <DiscoveryFooter />
      </div>

      {/* -------- Floating Map Action Button -------- */}
      <NavLink className="home-floating-fab" to="/catalogue">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
          <line x1="8" y1="2" x2="8" y2="18" />
          <line x1="16" y1="6" x2="16" y2="22" />
        </svg>
        Browse all scholarships
      </NavLink>
    </main>
  );
}
