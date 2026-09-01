import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import {
  AustraliaLandmarkSvg,
  CanadaLandmarkSvg,
  GermanyLandmarkSvg,
  UKLandmarkSvg,
  USLandmarkSvg,
} from "../../components/DestinationLandmarks";
import {
  type DegreeLevel,
  type FundingType,
} from "../catalogue/types";

/* ------------------------------------------------------------------ */
/*  Types & Options                                                   */
/* ------------------------------------------------------------------ */

export interface HomeSearchState {
  country: string;
  degree_level: DegreeLevel | "";
  funding_type: FundingType | "";
}

export type ActivePopover = "where" | "degree" | "funding" | null;

export const initialSearch: HomeSearchState = {
  country: "",
  degree_level: "",
  funding_type: "",
};

export const popularDestinations = [
  { country: "Germany", flag: "🇩🇪", hint: "DAAD, Free tuition public universities" },
  { country: "United States", flag: "🇺🇸", hint: "Fulbright, Harvard, MIT" },
  { country: "United Kingdom", flag: "🇬🇧", hint: "Chevening, Oxford, Cambridge" },
  { country: "Canada", flag: "🇨🇦", hint: "Vanier, Toronto, McGill" },
  { country: "Australia", flag: "🇦🇺", hint: "Australia Awards, Melbourne" },
  { country: "Europe", flag: "🇪🇺", hint: "Erasmus Mundus Joint Masters" },
];

export const degreeOptions: { label: string; value: DegreeLevel | ""; icon: string; desc: string }[] = [
  { label: "All Degree Levels", value: "", icon: "🌐", desc: "Bachelor's, Master's, PhD" },
  { label: "Bachelor's", value: "bachelors", icon: "🎓", desc: "Undergraduate & freshman grants" },
  { label: "Master's", value: "masters", icon: "📚", desc: "Postgraduate & professional degrees" },
  { label: "PhD / Doctorate", value: "phd", icon: "🔬", desc: "Research fellowships & doctorates" },
  { label: "Postdoc", value: "postdoc", icon: "🧪", desc: "Postdoctoral scientific research" },
  { label: "Short course", value: "short_course", icon: "⚡", desc: "Summer schools & training" },
];

export const fundingOptions: { label: string; value: FundingType | ""; icon: string; desc: string }[] = [
  { label: "All Funding Types", value: "", icon: "💎", desc: "Fully funded, Partial, etc." },
  { label: "Fully Funded", value: "full", icon: "🏆", desc: "Tuition + monthly living stipend + flights" },
  { label: "Partial Funding", value: "partial", icon: "💵", desc: "Tuition discount or partial stipend" },
  { label: "Tuition Only", value: "tuition_only", icon: "🏛️", desc: "100% tuition waiver coverage" },
  { label: "Stipend Only", value: "stipend_only", icon: "💳", desc: "Monthly living allowance grant" },
];

/* ------------------------------------------------------------------ */
/*  Featured Scholarships Data                                        */
/* ------------------------------------------------------------------ */

interface FeaturedScholarshipItem {
  id: string;
  name: string;
  country: string;
  flag: string;
  degreeLevel: string;
  deadline: string;
  matchScore: string;
  isFullMatch?: boolean;
}

const featuredScholarshipsData: FeaturedScholarshipItem[] = [
  {
    id: "daad-epos",
    name: "DAAD Development-Related Postgraduate Courses",
    country: "Germany",
    flag: "🇩🇪",
    degreeLevel: "Master's, PhD",
    deadline: "31 Oct 2026",
    matchScore: "Full Match",
    isFullMatch: true,
  },
  {
    id: "fulbright-foreign",
    name: "Fulbright Foreign Student Program",
    country: "United States",
    flag: "🇺🇸",
    degreeLevel: "Master's, PhD",
    deadline: "15 Oct 2026",
    matchScore: "90% Match",
  },
  {
    id: "chevening-uk",
    name: "Chevening Scholarships 2025/26",
    country: "United Kingdom",
    flag: "🇬🇧",
    degreeLevel: "Master's",
    deadline: "06 Nov 2026",
    matchScore: "90% Match",
  },
  {
    id: "vanier-canada",
    name: "Vanier Canada Graduate Scholarships",
    country: "Canada",
    flag: "🇨🇦",
    degreeLevel: "PhD",
    deadline: "05 Nov 2026",
    matchScore: "88% Match",
  },
  {
    id: "australia-awards",
    name: "Australia Awards Scholarships",
    country: "Australia",
    flag: "🇦🇺",
    degreeLevel: "Master's, PhD",
    deadline: "30 Apr 2027",
    matchScore: "86% Match",
  },
];

/* ------------------------------------------------------------------ */
/*  Browse by Destination Data                                        */
/* ------------------------------------------------------------------ */

interface DestinationCardItem {
  id: string;
  name: string;
  shortName: string;
  opportunitiesCount: string;
  subtitle: string;
  gradientClass: string;
  searchCountry: string;
  svgComponent: React.ComponentType<{ className?: string }>;
}

const destinationCardsData: DestinationCardItem[] = [
  {
    id: "uk",
    name: "United Kingdom",
    shortName: "UK",
    opportunitiesCount: "120+ opportunities",
    subtitle: "Study in world-class universities",
    gradientClass: "tns-dest-uk",
    searchCountry: "United Kingdom",
    svgComponent: UKLandmarkSvg,
  },
  {
    id: "us",
    name: "United States",
    shortName: "US",
    opportunitiesCount: "120+ opportunities",
    subtitle: "Top-ranked universities and research programs",
    gradientClass: "tns-dest-us",
    searchCountry: "United States",
    svgComponent: USLandmarkSvg,
  },
  {
    id: "germany",
    name: "Germany",
    shortName: "Germany",
    opportunitiesCount: "110+ opportunities",
    subtitle: "Tuition-free education in public universities",
    gradientClass: "tns-dest-germany",
    searchCountry: "Germany",
    svgComponent: GermanyLandmarkSvg,
  },
  {
    id: "canada",
    name: "Canada",
    shortName: "Canada",
    opportunitiesCount: "90+ opportunities",
    subtitle: "Diverse programs with strong support",
    gradientClass: "tns-dest-canada",
    searchCountry: "Canada",
    svgComponent: CanadaLandmarkSvg,
  },
  {
    id: "australia",
    name: "Australia",
    shortName: "Australia",
    opportunitiesCount: "80+ opportunities",
    subtitle: "Quality education and vibrant communities",
    gradientClass: "tns-dest-australia",
    searchCountry: "Australia",
    svgComponent: AustraliaLandmarkSvg,
  },
];

/* ------------------------------------------------------------------ */
/*  How It Works Step Data                                            */
/* ------------------------------------------------------------------ */

const howItWorksSteps = [
  {
    number: "1",
    title: "Discover",
    description: "Search verified scholarships tailored to your goals.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    number: "2",
    title: "Save",
    description: "Save opportunities you like and organize them in one place.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
      </svg>
    ),
  },
  {
    number: "3",
    title: "Track",
    description: "Track deadlines, requirements and application progress effortlessly.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="m19 9-5 5-4-4-3 3" />
      </svg>
    ),
  },
  {
    number: "4",
    title: "Prepare",
    description: "Get AI-powered guidance to build stronger applications and essays.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z" />
      </svg>
    ),
  },
];

/* ------------------------------------------------------------------ */
/*  Trust Bar Items                                                   */
/* ------------------------------------------------------------------ */

const trustMetrics = [
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    ),
    bold: "500+",
    label: "Verified Scholarships",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    ),
    bold: "120+",
    label: "Countries",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
        <path d="M6 12v5c3 3 9 3 12 0v-5" />
      </svg>
    ),
    bold: "Bachelor • Master • PhD",
    label: "All Degree Levels",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    ),
    bold: "Fully Funded",
    label: "Opportunities",
  },
];

/* ------------------------------------------------------------------ */
/*  Search Pill Component (Exact Airbnb Hover & Active Mechanics)       */
/* ------------------------------------------------------------------ */

function SegmentClearButton({
  label,
  onClear,
}: {
  label: string;
  onClear: () => void;
}) {
  return (
    <button
      type="button"
      className="tns-segment-clear"
      aria-label={label}
      onClick={(event) => {
        event.stopPropagation();
        onClear();
      }}
    >
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <path
          d="M9.5 2.5 2.5 9.5M2.5 2.5l7 7"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    </button>
  );
}

export function SearchPill({
  search,
  activePopover,
  onSearchChange,
  onPopoverChange,
}: {
  search: HomeSearchState;
  activePopover: ActivePopover;
  onSearchChange: (update: HomeSearchState | ((prev: HomeSearchState) => HomeSearchState)) => void;
  onPopoverChange: (popover: ActivePopover) => void;
}) {
  const navigate = useNavigate();
  const searchContainerRef = useRef<HTMLDivElement>(null);
  const pillRef = useRef<HTMLFormElement>(null);
  const whereRef = useRef<HTMLDivElement>(null);
  const degreeRef = useRef<HTMLDivElement>(null);
  const fundingRef = useRef<HTMLDivElement>(null);
  const whereInputRef = useRef<HTMLInputElement>(null);
  const [hoveredSegment, setHoveredSegment] = useState<Exclude<ActivePopover, null> | null>(null);
  const [highlight, setHighlight] = useState({ left: 0, width: 0, visible: false });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    onPopoverChange(null);
    const params = new URLSearchParams();
    if (search.country) params.set("country", search.country);
    if (search.degree_level) params.set("degree_level", search.degree_level);
    if (search.funding_type) params.set("funding_type", search.funding_type);
    navigate(`/catalogue?${params.toString()}`);
  }

  const isAnyActive = activePopover !== null;
  const openPopover = (popover: Exclude<ActivePopover, null>) => {
    onPopoverChange(activePopover === popover ? null : popover);
  };

  const handleSegmentKey =
    (popover: Exclude<ActivePopover, null>) => (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPopover(popover);
      }
    };

  useLayoutEffect(() => {
    const pill = pillRef.current;
    if (!pill) return;

    function measure() {
      const refs = { where: whereRef, degree: degreeRef, funding: fundingRef };
      const el = activePopover ? refs[activePopover].current : null;
      if (!el || !pill) {
        setHighlight((current) => ({ ...current, visible: false }));
        return;
      }
      const pillBox = pill.getBoundingClientRect();
      const box = el.getBoundingClientRect();
      setHighlight({
        left: box.left - pillBox.left,
        width: box.width,
        visible: true,
      });
    }

    measure();
    const frame = window.requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    observer.observe(pill);
    window.addEventListener("resize", measure);

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [activePopover, search.country, search.degree_level, search.funding_type]);

  useEffect(() => {
    if (activePopover === "where") {
      whereInputRef.current?.focus();
    }
  }, [activePopover]);

  useEffect(() => {
    if (!activePopover) return;

    function handleOutsideClick(event: MouseEvent) {
      if (!searchContainerRef.current?.contains(event.target as Node)) {
        onPopoverChange(null);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onPopoverChange(null);
      }
    }

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [activePopover, onPopoverChange]);

  const destinationQuery = search.country.trim().toLowerCase();
  const filteredDestinations = popularDestinations.filter(
    (destination) =>
      !destinationQuery ||
      destination.country.toLowerCase().includes(destinationQuery) ||
      destination.hint.toLowerCase().includes(destinationQuery),
  );
  const showAnywhere =
    !destinationQuery || "anywhere".includes(destinationQuery) || "every destination".includes(destinationQuery);

  function showClear(segment: Exclude<ActivePopover, null>, hasValue: boolean) {
    return hasValue && (activePopover === segment || hoveredSegment === segment);
  }

  return (
    <div className={`tns-search-container ${isAnyActive ? "tns-search-container--open" : ""}`} ref={searchContainerRef}>
      <div className="tns-mobile-airbnb-shell">
        <button
          className="tns-mobile-start-search"
          type="button"
          onClick={() => onPopoverChange(activePopover ? null : "where")}
          aria-expanded={isAnyActive}
        >
          <span className="tns-mobile-start-icon" aria-hidden="true">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>
          <span>Start your search</span>
        </button>

        <div className="tns-mobile-category-tabs" aria-label="Scholarship search shortcuts">
          <button type="button" className="tns-mobile-category-chip is-active">🎓 All</button>
          <button type="button" className="tns-mobile-category-chip">🏛️ Degree</button>
          <button type="button" className="tns-mobile-category-chip">💎 Funding</button>
          <button type="button" className="tns-mobile-category-chip">🌍 Country</button>
        </div>
      </div>

      {/* Desktop Airbnb Search Pill */}
      <form
        className={`tns-airbnb-search-pill ${isAnyActive ? "has-active-segment" : ""}`}
        onSubmit={handleSubmit}
        role="search"
        aria-label="Search verified scholarships"
      >
        {/* Segment 1: Where */}
        <div
          className={`tns-airbnb-segment segment-where ${activePopover === "where" ? "is-active" : ""}`}
          onClick={() => openPopover("where")}
          onKeyDown={handleSegmentKey("where")}
          role="button"
          tabIndex={0}
        >
          <div className="tns-segment-text-col">
            <span className="tns-segment-label">Where</span>
            <span className={`tns-segment-input ${search.country ? "is-filled" : ""}`}>
              {search.country || "Search destinations"}
            </span>
          </div>
          <div className="tns-search-divider" aria-hidden="true" />
        </div>

        {/* Segment 2: Degree Level */}
        <div
          className={`tns-airbnb-segment segment-degree ${activePopover === "degree" ? "is-active" : ""}`}
          onClick={() => openPopover("degree")}
          onKeyDown={handleSegmentKey("degree")}
          role="button"
          tabIndex={0}
        >
          <div className="tns-segment-text-col">
            <span className="tns-segment-label">Degree level</span>
            <span className={`tns-segment-input ${search.degree_level ? "is-filled" : ""}`}>
              {search.degree_level
                ? degreeOptions.find((d) => d.value === search.degree_level)?.label
                : "Bachelor's, Master's, PhD"}
            </span>
          </div>
          <div className="tns-search-divider" aria-hidden="true" />
        </div>

        {/* Segment 3: Funding Type + Search Button Wrap */}
        <div
          className={`tns-airbnb-segment segment-funding ${activePopover === "funding" ? "is-active" : ""}`}
          onClick={() => openPopover("funding")}
          onKeyDown={handleSegmentKey("funding")}
          role="button"
          tabIndex={0}
        >
          <div className="tns-segment-text-col">
            <span className="tns-segment-label">Funding type</span>
            <span className={`tns-segment-input ${search.funding_type ? "is-filled" : ""}`}>
              {search.funding_type
                ? fundingOptions.find((f) => f.value === search.funding_type)?.label
                : "Fully funded, Partial, etc."}
            </span>
          </div>

          {/* Search Button wrapped inside segment 3 */}
          <button
            type="submit"
            className="tns-search-submit-btn"
            aria-label="Search scholarships"
            onClick={(e) => e.stopPropagation()}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <span className="tns-search-btn-text">Search</span>
          </button>
        </div>
      </form>

      <div className="tns-desktop-popover-layer" aria-live="polite">
        {wherePopover}
        {degreePopover}
        {fundingPopover}
      </div>

      {/* Mobile Search Card (Hidden on Desktop) */}
      <form
        className={`tns-mobile-search-card ${isAnyActive ? "tns-mobile-search-card--open" : ""}`}
        onSubmit={handleSubmit}
        role="dialog"
        aria-label="Scholarship search"
      >
        <div className="tns-mobile-sheet-top">
          <h3>Where?</h3>
          <button
            type="button"
            className="tns-mobile-sheet-close"
            onClick={() => onPopoverChange(null)}
            aria-label="Close scholarship search"
          >
            ✕
          </button>
        </div>
        <div className="tns-mobile-search-row">
          <span className="tns-mobile-search-icon">🔍</span>
          <div className="tns-mobile-search-field">
            <label className="tns-mobile-field-label">Where</label>
            <input
              type="text"
              className="tns-mobile-input"
              placeholder="Search destinations"
              value={search.country}
              onChange={(e) => onSearchChange((s) => ({ ...s, country: e.target.value }))}
            />
          </div>
        </div>

        <div className="tns-mobile-search-row">
          <span className="tns-mobile-search-icon">🎓</span>
          <div className="tns-mobile-search-field">
            <label className="tns-mobile-field-label">Degree level</label>
            <select
              className="tns-mobile-select"
              value={search.degree_level}
              onChange={(e) => onSearchChange((s) => ({ ...s, degree_level: e.target.value as DegreeLevel }))}
            >
              {degreeOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="tns-mobile-search-row">
          <span className="tns-mobile-search-icon">💎</span>
          <div className="tns-mobile-search-field">
            <label className="tns-mobile-field-label">Funding type</label>
            <select
              className="tns-mobile-select"
              value={search.funding_type}
              onChange={(e) => onSearchChange((s) => ({ ...s, funding_type: e.target.value as FundingType }))}
            >
              <option value="">Fully funded, Partial, etc.</option>
              <option value="full">Fully Funded</option>
              <option value="partial">Partial Aid</option>
              <option value="tuition_only">Tuition Only</option>
              <option value="stipend_only">Stipend Only</option>
            </select>
          </div>
        </div>

        <button type="submit" className="tns-mobile-search-btn">
          <span>Search scholarships</span>
        </button>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main HomePage Component                                           */
/* ------------------------------------------------------------------ */

export function HomePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [savedFavorites, setSavedFavorites] = useState<Set<string>>(new Set(["daad-epos"]));

  function toggleFavorite(id: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    setSavedFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  return (
    <main className="tns-home-layout">
      {/* ------------------------------------------------------------ */}
      {/*  HERO SECTION (Clean document flow directly below header)     */}
      {/* ------------------------------------------------------------ */}
      <section className="tns-hero-section">
        <div className="page-width tns-hero-content">
          <div className="tns-hero-sparkles-container">
            <span className="tns-sparkle tns-sparkle-left" aria-hidden="true">✦</span>
            <h1 className="tns-hero-heading">
              <span className="tns-hero-title-dark">Find scholarships.</span>
              <br />
              <span className="tns-hero-title-crimson">Build stronger applications.</span>
            </h1>
            <span className="tns-sparkle tns-sparkle-right" aria-hidden="true">✦</span>
          </div>

          <p className="tns-hero-subtitle">
            Discover 50,000+ verified scholarships worldwide
            <br />
            and get AI-powered guidance to win more.
          </p>

          {/* Sub-CTA Pill */}
          <div className="tns-hero-sub-cta">
            <NavLink
              to={user ? "/matches" : "/profile"}
              className="tns-match-profile-btn"
            >
              <span className="tns-sparkle-icon" aria-hidden="true">✨</span>
              <span>Find scholarships that match my profile</span>
            </NavLink>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ */}
      {/*  AI-POWERED MATCHING FEATURE BANNER                          */}
      {/* ------------------------------------------------------------ */}
      <section className="page-width tns-ai-banner-wrapper">
        <div className="tns-ai-banner">
          <div className="tns-ai-banner-left">
            <div className="tns-ai-badge">
              <span aria-hidden="true">✨</span>
              <span>AI POWERED</span>
            </div>

            <h2 className="tns-ai-banner-title">
              Not sure which scholarships you qualify for?
            </h2>

            <p className="tns-ai-banner-desc">
              Our AI analyzes verified criteria and your profile to surface the best
              matches and give you personalized guidance.
            </p>

            <div className="tns-ai-banner-actions">
              <NavLink to="/assistant" className="tns-btn-crimson">
                <span>Open assistant</span>
                <span aria-hidden="true">›</span>
              </NavLink>
              <button
                type="button"
                className="tns-btn-ghost-white"
                onClick={() => {
                  const el = document.getElementById("how-it-works");
                  el?.scrollIntoView({ behavior: "smooth" });
                }}
              >
                <span>See how matching works</span>
                <span className="tns-play-icon" aria-hidden="true">▶</span>
              </button>
            </div>
          </div>

          {/* Right Preview Match Cards with Circular Progress Meters */}
          <div className="tns-ai-banner-right">
            {/* Card 1: 87% Match */}
            <div className="tns-ai-gauge-card tns-gauge-card--side tns-gauge-card--left">
              <div className="tns-circular-meter">
                <svg viewBox="0 0 36 36" className="tns-circular-chart">
                  <path
                    className="tns-circle-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="tns-circle-stroke tns-stroke-cyan"
                    strokeDasharray="87, 100"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <div className="tns-meter-text">
                  <span className="tns-meter-pct">87%</span>
                  <span className="tns-meter-label">Match</span>
                </div>
              </div>
              <h3 className="tns-gauge-card-title">DAAD EPOS Scholarship</h3>
              <span className="tns-gauge-card-badge">Fully funded</span>
            </div>

            {/* Card 2: 94% Match (Hero Active Card with Glow) */}
            <div className="tns-ai-gauge-card tns-gauge-card--hero">
              <div className="tns-circular-meter tns-circular-meter--large">
                <svg viewBox="0 0 36 36" className="tns-circular-chart">
                  <path
                    className="tns-circle-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="tns-circle-stroke tns-stroke-teal"
                    strokeDasharray="94, 100"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <div className="tns-meter-text">
                  <span className="tns-meter-pct tns-meter-pct--large">94%</span>
                  <span className="tns-meter-label">Match</span>
                </div>
              </div>
              <h3 className="tns-gauge-card-title tns-gauge-card-title--hero">
                Erasmus Mundus Joint Master
              </h3>
              <span className="tns-gauge-card-badge tns-badge-mint">Fully funded</span>
            </div>

            {/* Card 3: 72% Match */}
            <div className="tns-ai-gauge-card tns-gauge-card--side tns-gauge-card--right">
              <div className="tns-circular-meter">
                <svg viewBox="0 0 36 36" className="tns-circular-chart">
                  <path
                    className="tns-circle-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path
                    className="tns-circle-stroke tns-stroke-blue"
                    strokeDasharray="72, 100"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <div className="tns-meter-text">
                  <span className="tns-meter-pct">72%</span>
                  <span className="tns-meter-label">Match</span>
                </div>
              </div>
              <h3 className="tns-gauge-card-title">Commonwealth Master's</h3>
              <span className="tns-gauge-card-badge">Partial funding</span>
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ */}
      {/*  FEATURED SCHOLARSHIPS SECTION                               */}
      {/* ------------------------------------------------------------ */}
      <section className="page-width tns-section">
        <div className="tns-section-header">
          <h2 className="tns-section-title">Featured scholarships</h2>
          <NavLink to="/catalogue" className="tns-section-link">
            <span>View all scholarships</span>
            <span aria-hidden="true">›</span>
          </NavLink>
        </div>

        <div className="tns-featured-carousel">
          {featuredScholarshipsData.map((item) => {
            const isFav = savedFavorites.has(item.id);
            const matchLabel = user ? item.matchScore : "Check eligibility";
            return (
              <div key={item.id} className="tns-scholarship-card">
                <div className="tns-card-top-row">
                  <div className="tns-card-country-badge">
                    <span className="tns-flag" aria-hidden="true">{item.flag}</span>
                    <span className="tns-country-name">{item.country}</span>
                  </div>
                  <button
                    type="button"
                    className={`tns-favorite-btn ${isFav ? "active" : ""}`}
                    onClick={(e) => toggleFavorite(item.id, e)}
                    aria-label={isFav ? `Remove ${item.name} from saved` : `Save ${item.name}`}
                  >
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill={isFav ? "#E11D48" : "none"}
                      stroke={isFav ? "#E11D48" : "currentColor"}
                      strokeWidth="2"
                    >
                      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
                    </svg>
                  </button>
                </div>

                <h3 className="tns-card-title">
                  <Link to={`/catalogue?country=${encodeURIComponent(item.country)}`}>
                    {item.name}
                  </Link>
                </h3>

                <div className="tns-card-meta-list">
                  <div className="tns-card-meta-item">
                    <span className="tns-meta-icon" aria-hidden="true">🎓</span>
                    <span>{item.degreeLevel}</span>
                  </div>
                  <div className="tns-card-meta-item">
                    <span className="tns-meta-icon" aria-hidden="true">📅</span>
                    <span className="tns-meta-deadline">
                      <span className="tns-deadline-label">Deadline: </span>
                      {item.deadline}
                    </span>
                  </div>
                </div>

                <div className="tns-card-footer">
                  <span className={`tns-match-pill ${user && item.isFullMatch ? "tns-match-pill--full" : ""} ${!user ? "tns-match-pill--locked" : ""}`}>
                    {matchLabel}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ------------------------------------------------------------ */}
      {/*  BROWSE BY DESTINATION SECTION                               */}
      {/* ------------------------------------------------------------ */}
      <section className="page-width tns-section">
        <div className="tns-section-header">
          <h2 className="tns-section-title">Browse by destination</h2>
          <NavLink to="/catalogue" className="tns-section-link">
            <span>See all destinations</span>
            <span aria-hidden="true">›</span>
          </NavLink>
        </div>

        <div className="tns-destination-grid">
          {destinationCardsData.map((dest) => {
            const Landmark = dest.svgComponent;
            return (
              <button
                key={dest.id}
                type="button"
                className={`tns-destination-card ${dest.gradientClass}`}
                onClick={() => navigate(`/catalogue?country=${encodeURIComponent(dest.searchCountry)}`)}
              >
                <div className="tns-dest-card-content">
                  <h3 className="tns-dest-name">{dest.shortName}</h3>
                  <p className="tns-dest-count">{dest.opportunitiesCount}</p>
                  <p className="tns-dest-subtitle">{dest.subtitle}</p>

                  <div className="tns-dest-arrow-btn" aria-hidden="true">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="5" y1="12" x2="19" y2="12" />
                      <polyline points="12 5 19 12 12 19" />
                    </svg>
                  </div>
                </div>

                <div className="tns-dest-landmark-art" aria-hidden="true">
                  <Landmark />
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* ------------------------------------------------------------ */}
      {/*  HOW IT WORKS SECTION                                        */}
      {/* ------------------------------------------------------------ */}
      <section id="how-it-works" className="page-width tns-section tns-how-section">
        <h2 className="tns-section-title tns-text-center">How it works</h2>

        <div className="tns-how-grid">
          {howItWorksSteps.map((step) => (
            <div key={step.number} className="tns-how-card">
              <div className="tns-how-card-header">
                <span className="tns-step-title">{step.title}</span>
                <div className="tns-how-card-icon-wrapper">{step.icon}</div>
              </div>
              <p className="tns-how-card-desc">{step.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ */}
      {/*  TRUST & METRICS BAR                                         */}
      {/* ------------------------------------------------------------ */}
      <section className="page-width tns-trust-bar-section">
        <div className="tns-trust-bar">
          {trustMetrics.map((m, idx) => (
            <div key={idx} className="tns-trust-item">
              <span className="tns-trust-icon" aria-hidden="true">{m.icon}</span>
              <div className="tns-trust-text">
                <strong className="tns-trust-bold">{m.bold}</strong>
                <span className="tns-trust-label">{m.label}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ */}
      {/*  COMPREHENSIVE FOOTER                                        */}
      {/* ------------------------------------------------------------ */}
      <footer className="tns-footer">
        <div className="page-width tns-footer-content">
          <div className="tns-footer-brand-col">
            <h3 style={{ color: "var(--tns-crimson)", fontWeight: 800, fontSize: "1.2rem" }}>the next scholar</h3>
            <p className="tns-footer-tagline">
              AI-powered scholarship matching to help you study anywhere.
            </p>
          </div>

          <div className="tns-footer-links-grid">
            <div className="tns-footer-col">
              <h4 className="tns-footer-heading">Explore</h4>
              <ul className="tns-footer-list">
                <li><NavLink to="/catalogue">All Scholarships</NavLink></li>
                <li><NavLink to="/catalogue?country=Germany">By Country</NavLink></li>
                <li><NavLink to="/catalogue?degree_level=masters">By Degree</NavLink></li>
                <li><NavLink to="/catalogue?funding_type=full">By Funding Type</NavLink></li>
              </ul>
            </div>

            <div className="tns-footer-col">
              <h4 className="tns-footer-heading">Company</h4>
              <ul className="tns-footer-list">
                <li><NavLink to="/">About Us</NavLink></li>
                <li><NavLink to="/">Careers</NavLink></li>
                <li><NavLink to="/">Blog</NavLink></li>
                <li><NavLink to="/">Press</NavLink></li>
              </ul>
            </div>

            <div className="tns-footer-col">
              <h4 className="tns-footer-heading">Support</h4>
              <ul className="tns-footer-list">
                <li><NavLink to="/">Help Center</NavLink></li>
                <li><NavLink to="/">Contact Us</NavLink></li>
                <li><NavLink to="/">Privacy Policy</NavLink></li>
                <li><NavLink to="/">Terms of Service</NavLink></li>
              </ul>
            </div>

            <div className="tns-footer-col" id="for-students">
              <h4 className="tns-footer-heading">For Students</h4>
              <ul className="tns-footer-list">
                <li><NavLink to="/#how-it-works">How it Works</NavLink></li>
                <li><NavLink to="/assistant">Application Tips</NavLink></li>
                <li><NavLink to="/matches">Success Stories</NavLink></li>
                <li><NavLink to="/applications">Scholarship Tracker</NavLink></li>
              </ul>
            </div>
          </div>
        </div>

        <div className="tns-footer-bottom">
          <p>© 2025 The Next Scholar (thenextscholar.com). All rights reserved.</p>
        </div>
      </footer>
    </main>
  );
}
