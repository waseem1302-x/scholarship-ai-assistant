import { useState } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { getHomepageJourneySections } from "./homepageJourneyContent";
import { HomepageJourneySection } from "./HomepageJourneySection";

const erasmusHeroImage = new URL("../../assets/hero/erasmus-campus-highres.jpg", import.meta.url).href;

export function HomePage() {
  const { user, isRestoring } = useAuth();
  const [savedFavorites, setSavedFavorites] = useState<Set<string>>(() => new Set());
  const journeySections = getHomepageJourneySections(Boolean(user));

  function toggleFavorite(id: string) {
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

  if (isRestoring) {
    return (
      <main className="page-width loading-page" aria-live="polite">
        Restoring your scholarship journey...
      </main>
    );
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

      <div className="tns-home-journey" aria-label="Your scholarship journey">
        {journeySections.map((section) => (
          <HomepageJourneySection
            key={section.id}
            section={section}
            savedFavorites={savedFavorites}
            onToggleFavorite={toggleFavorite}
          />
        ))}
      </div>

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
