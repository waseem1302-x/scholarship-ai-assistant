import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import {
  AustraliaLandmarkSvg,
  CanadaLandmarkSvg,
  GermanyLandmarkSvg,
  UKLandmarkSvg,
  USLandmarkSvg,
} from "../../components/DestinationLandmarks";

const erasmusHeroImage = new URL("../../assets/hero/erasmus-campus-highres.jpg", import.meta.url).href;
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
      <section className="tns-hero-section" aria-label="Find scholarships that fit you">
        <div className="page-width tns-hero-content">
          <div className="tns-hero-copy">
            <div className="tns-hero-badge">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="8" cy="8" r="3" />
                <path d="M3.5 18c.8-3.1 2.3-4.7 4.5-4.7s3.7 1.6 4.5 4.7M16 6l.8 1.8L19 8.5l-2.2.8L16 11l-.8-1.7-2.2-.8 2.2-.7L16 6Z" />
              </svg>
              <span>Scholarship matching, built around you</span>
            </div>

            <h1 className="tns-hero-heading" id="tns-hero-title">
              <span className="tns-hero-title-dark">Find scholarships</span>
              <span className="tns-hero-title-crimson">that fit you.</span>
            </h1>

            <p className="tns-hero-subtitle">
              Create your profile once. We compare it with verified eligibility criteria,
              <br className="tns-hero-desktop-break" /> so you can focus on opportunities worth pursuing.
            </p>

            <div className="tns-hero-stats" aria-label="How scholarship matching helps">
              <div className="tns-hero-stat">
                <span className="tns-stat-icon tns-stat-icon--blue" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <circle cx="12" cy="8" r="3.5" />
                    <path d="M5 20c.8-4.2 3.1-6.3 7-6.3s6.2 2.1 7 6.3" />
                  </svg>
                </span>
                <span className="tns-stat-copy"><strong>Profile once</strong><span>Save your background</span></span>
              </div>
              <div className="tns-hero-stat">
                <span className="tns-stat-icon tns-stat-icon--mint" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M7 3.5h10v17H7zM9.5 3.5v-1h5v1" />
                    <path d="m9.5 12 1.8 1.8 3.8-4" />
                  </svg>
                </span>
                <span className="tns-stat-copy"><strong>Verified criteria</strong><span>Check real requirements</span></span>
              </div>
              <div className="tns-hero-stat">
                <span className="tns-stat-icon tns-stat-icon--peach" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M4 12s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5Z" />
                    <circle cx="12" cy="12" r="2" />
                  </svg>
                </span>
                <span className="tns-stat-copy"><strong>Clear reasons</strong><span>Understand every match</span></span>
              </div>
            </div>

            <div className="tns-hero-actions">
              <NavLink to={user ? "/matches" : "/profile"} className="tns-hero-cta tns-hero-cta--primary">
                <span>Find My Matches</span>
                <span aria-hidden="true">→</span>
              </NavLink>
              <NavLink to="/scholarships" className="tns-hero-cta tns-hero-cta--secondary">
                <span>Explore Scholarships</span>
                <span aria-hidden="true">→</span>
              </NavLink>
            </div>

            <div className="tns-hero-assurance">
              <span className="tns-hero-assurance-icon" aria-hidden="true">✓</span>
              <p><strong>Your context stays with you.</strong><span>No repeated background every time you search.</span></p>
            </div>
          </div>

          <div className="tns-hero-visual" aria-label="How your profile becomes a scholarship match">
            <div className="tns-hero-visual-glow" aria-hidden="true" />

            <aside className="tns-profile-preview" aria-label="Example student profile">
              <div className="tns-profile-preview-head">
                <span className="tns-profile-avatar" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <circle cx="12" cy="8" r="3.5" />
                    <path d="M5 20c.8-4.2 3.1-6.3 7-6.3s6.2 2.1 7 6.3" />
                  </svg>
                </span>
                <span><small>Your profile</small><strong>Ready to match</strong></span>
              </div>
              <p>Saved once, ready for every opportunity.</p>
              <dl className="tns-profile-facts">
                <div><dt>Education</dt><dd>Bachelor&apos;s degree</dd></div>
                <div><dt>Field</dt><dd>Computer Science</dd></div>
                <div><dt>Study goal</dt><dd>Master&apos;s abroad</dd></div>
              </dl>
            </aside>

            <div className="tns-match-route" aria-hidden="true">
              <svg viewBox="0 0 100 100" preserveAspectRatio="none">
                <path d="M 0 100 C 0 10, 28 0, 100 0" />
              </svg>
              <span>How it works</span>
            </div>

            <div className="tns-match-bridge" aria-hidden="true">
              <span>✓</span>
            </div>

            <article className="tns-fit-preview">
              <div className="tns-fit-preview-media">
                <img src={erasmusHeroImage} alt="Historic European university campus" />
                <span className="tns-fit-strength"><span aria-hidden="true">✓</span> Strong match</span>
              </div>
              <div className="tns-fit-preview-body">
                <span className="tns-fit-eyebrow">Recommended opportunity</span>
                <h2>Erasmus Mundus Joint Master</h2>
                <div className="tns-fit-meta">
                  <span><span className="tns-hero-flag tns-hero-flag--eu" aria-hidden="true">✦</span>Europe</span>
                  <span className="tns-tag tns-tag--funded">Fully funded</span>
                </div>
                <div className="tns-fit-reasons">
                  <div className="tns-fit-reasons-head">
                    <strong>Why it fits</strong>
                    <span>3 criteria aligned</span>
                  </div>
                  <ul>
                    <li><span aria-hidden="true">✓</span>Degree requirement met</li>
                    <li><span aria-hidden="true">✓</span>Field aligned</li>
                    <li><span aria-hidden="true">✓</span>Open to your nationality</li>
                  </ul>
                </div>
                <NavLink to="/scholarships" className="tns-fit-link">
                  <span>View match details</span><span aria-hidden="true">→</span>
                </NavLink>
              </div>
            </article>

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
