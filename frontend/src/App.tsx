import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { EmailVerificationNotice } from "./auth/AccountLifecycle";
import { AuthForm, AuthProvider, useAuth } from "./auth/AuthProvider";
import { Brand } from "./components/BrandLogo";
import { ScholarshipSearch } from "./components/ScholarshipSearch";
import { HomePage, initialSearch, type ActivePopover } from "./features/home/HomePage";

const EmailVerificationPage = lazy(() => import("./auth/AccountLifecycle").then((m) => ({ default: m.EmailVerificationPage })));
const PasswordResetPage = lazy(() => import("./auth/AccountLifecycle").then((m) => ({ default: m.PasswordResetPage })));
const CataloguePage = lazy(() => import("./features/catalogue/CataloguePage").then((m) => ({ default: m.CataloguePage })));
const OpportunityDetailPage = lazy(() => import("./features/catalogue/OpportunityDetailPage").then((m) => ({ default: m.OpportunityDetailPage })));
const AdminPage = lazy(() => import("./features/admin/AdminPage").then((m) => ({ default: m.AdminPage })));
const AdminSecurityPage = lazy(() => import("./features/admin/AdminSecurityPage").then((m) => ({ default: m.AdminSecurityPage })));
const MatchesPage = lazy(() => import("./features/workspace/MatchesPage").then((m) => ({ default: m.MatchesPage })));
const ProfilePage = lazy(() => import("./features/workspace/ProfilePage").then((m) => ({ default: m.ProfilePage })));
const CommandCentrePage = lazy(() => import("./features/workspace/CommandCentrePage").then((m) => ({ default: m.CommandCentrePage })));
const ApplicationDetailPage = lazy(() => import("./features/workspace/ApplicationDetailPage").then((m) => ({ default: m.ApplicationDetailPage })));
const AssistantPage = lazy(() => import("./features/assistant/AssistantPage").then((m) => ({ default: m.AssistantPage })));
const DocumentLabPage = lazy(() => import("./features/document-lab/DocumentLabPage").then((m) => ({ default: m.DocumentLabPage })));
const CommunityPage = lazy(() => import("./features/community/CommunityPage").then((m) => ({ default: m.CommunityPage })));

export function Topbar() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isHome = location.pathname === "/";
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [search, setSearch] = useState(initialSearch);
  const [activePopover, setActivePopover] = useState<ActivePopover>(null);
  const [homeSearchCompact, setHomeSearchCompact] = useState(false);

  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMenuOpen(false);
    setMobileDrawerOpen(false);
    setActivePopover(null);

    if (location.hash) {
      const targetId = location.hash.replace("#", "");
      const element = document.getElementById(targetId);
      if (element) {
        window.setTimeout(() => {
          element.scrollIntoView({ behavior: "smooth" });
        }, 120);
      }
    }
  }, [location.pathname, location.hash]);

  useEffect(() => {
    if (!isHome) {
      setHomeSearchCompact(false);
      return;
    }

    let frame = 0;

    function updateHeaderSearchState() {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        setHomeSearchCompact(window.scrollY > 72);
      });
    }

    updateHeaderSearchState();
    window.addEventListener("scroll", updateHeaderSearchState, { passive: true });

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", updateHeaderSearchState);
    };
  }, [isHome]);

  useEffect(() => {
    if (!menuOpen) return;

    function handleOutsideClick(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [menuOpen]);

  async function logout() {
    setLogoutError(null);
    setIsSigningOut(true);
    try {
      await signOut();
      setMenuOpen(false);
      setMobileDrawerOpen(false);
      navigate("/");
    } catch {
      setLogoutError("We could not confirm server sign-out. Please try again.");
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <>
      <header
        className={[
          "tns-header",
          isHome ? "tns-header--home" : "",
          isHome && homeSearchCompact ? "tns-header--search-compact" : "",
          isHome && activePopover ? "tns-header--search-open" : "",
        ].filter(Boolean).join(" ")}
      >
        <div className="tns-nav-top page-width">
          <Brand />

          <nav className="tns-nav-center" aria-label="Product navigation">
            {!user ? (
              <>
                <NavLink
                  className={({ isActive }) => `tns-nav-link ${isActive ? "active" : ""}`}
                  to="/catalogue"
                >
                  Scholarships
                </NavLink>
                <a
                  className="tns-nav-link"
                  href="/#how-it-works"
                  onClick={(event) => {
                    if (location.pathname === "/") {
                      event.preventDefault();
                      document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" });
                    }
                  }}
                >
                  How it works
                </a>
                <a
                  className="tns-nav-link"
                  href="/#for-students"
                  onClick={(event) => {
                    if (location.pathname === "/") {
                      event.preventDefault();
                      document.getElementById("for-students")?.scrollIntoView({ behavior: "smooth" });
                    }
                  }}
                >
                  For students
                </a>
              </>
            ) : (
              <>
                <NavLink
                  className={({ isActive }) => `tns-nav-link ${isActive ? "active" : ""}`}
                  to="/catalogue"
                >
                  Scholarships
                </NavLink>
                <NavLink
                  className={({ isActive }) => `tns-nav-link ${isActive ? "active" : ""}`}
                  to="/matches"
                >
                  Matches
                </NavLink>
                <NavLink
                  className={({ isActive }) => `tns-nav-link ${isActive ? "active" : ""}`}
                  to="/applications"
                >
                  Applications
                </NavLink>
                <NavLink
                  className={({ isActive }) => `tns-nav-link ${isActive ? "active" : ""}`}
                  to="/assistant"
                >
                  Guidance
                </NavLink>
              </>
            )}
          </nav>

          <div className="tns-nav-right">
            {!user ? (
              <div className="tns-auth-actions">
                <NavLink className="tns-login-link" to="/auth">
                  Sign in
                </NavLink>
              </div>
            ) : (
              <div className="tns-user-menu-wrapper" ref={userMenuRef}>
                <button
                  className="tns-user-pill-btn"
                  type="button"
                  aria-label="User account menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((open) => !open)}
                >
                  <span className="tns-user-avatar">
                    {user.email.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="tns-user-email-short">
                    {user.email.split("@")[0]}
                  </span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                </button>

                {menuOpen ? (
                  <div className="tns-dropdown-menu" role="menu">
                    <NavLink className="tns-dropdown-item" to="/dashboard" onClick={() => setMenuOpen(false)} role="menuitem">
                      <strong>Dashboard</strong>
                    </NavLink>
                    <NavLink className="tns-dropdown-item" to="/applications" onClick={() => setMenuOpen(false)} role="menuitem">
                      Applications tracker
                    </NavLink>
                    <NavLink className="tns-dropdown-item" to="/matches" onClick={() => setMenuOpen(false)} role="menuitem">
                      Explainable matches
                    </NavLink>
                    <NavLink className="tns-dropdown-item" to="/profile" onClick={() => setMenuOpen(false)} role="menuitem">
                      Profile & criteria
                    </NavLink>
                    {user.role === "admin" ? (
                      <>
                        <div className="tns-dropdown-divider" />
                        <NavLink className="tns-dropdown-item" to="/admin" onClick={() => setMenuOpen(false)} role="menuitem">
                          Admin workspace
                        </NavLink>
                        <NavLink className="tns-dropdown-item" to="/admin/security" onClick={() => setMenuOpen(false)} role="menuitem">
                          Security & audit
                        </NavLink>
                      </>
                    ) : null}
                    <div className="tns-dropdown-divider" />
                    <button
                      className="tns-dropdown-item tns-logout-btn"
                      type="button"
                      onClick={logout}
                      disabled={isSigningOut}
                      role="menuitem"
                    >
                      {isSigningOut ? "Signing out..." : "Log out"}
                    </button>
                  </div>
                ) : null}
              </div>
            )}

            <button
              className="tns-mobile-hamburger-btn"
              type="button"
              aria-label="Toggle mobile menu"
              aria-expanded={mobileDrawerOpen}
              onClick={() => setMobileDrawerOpen((open) => !open)}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        {isHome ? (
          <div className="tns-header-search-bar page-width">
            <ScholarshipSearch
              search={search}
              activePopover={activePopover}
              onSearchChange={setSearch}
              onPopoverChange={setActivePopover}
            />
          </div>
        ) : null}

        {mobileDrawerOpen ? (
          <div className="tns-mobile-drawer" role="dialog" aria-modal="true" aria-label="Navigation menu">
            <div className="tns-mobile-drawer-header">
              <Brand onClick={() => setMobileDrawerOpen(false)} />
              <button
                type="button"
                className="tns-drawer-close-btn"
                onClick={() => setMobileDrawerOpen(false)}
                aria-label="Close menu"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
                  <line x1="6" y1="6" x2="18" y2="18" />
                  <line x1="18" y1="6" x2="6" y2="18" />
                </svg>
              </button>
            </div>
            <div className="tns-mobile-drawer-links">
              {!user ? (
                <>
                  <NavLink to="/catalogue" onClick={() => setMobileDrawerOpen(false)}>
                    Scholarships
                  </NavLink>
                  <a href="/#how-it-works" onClick={() => setMobileDrawerOpen(false)}>
                    How it works
                  </a>
                  <a href="/#for-students" onClick={() => setMobileDrawerOpen(false)}>
                    For students
                  </a>
                  <div className="tns-mobile-drawer-divider" />
                  <NavLink to="/auth" className="tns-mobile-login-link" onClick={() => setMobileDrawerOpen(false)}>
                    Sign in
                  </NavLink>
                </>
              ) : (
                <>
                  <NavLink to="/catalogue" onClick={() => setMobileDrawerOpen(false)}>
                    Scholarships
                  </NavLink>
                  <NavLink to="/matches" onClick={() => setMobileDrawerOpen(false)}>
                    Matches
                  </NavLink>
                  <NavLink to="/applications" onClick={() => setMobileDrawerOpen(false)}>
                    Applications
                  </NavLink>
                  <NavLink to="/assistant" onClick={() => setMobileDrawerOpen(false)}>
                    Guidance
                  </NavLink>
                  <NavLink to="/profile" onClick={() => setMobileDrawerOpen(false)}>
                    Profile & settings
                  </NavLink>
                  <div className="tns-mobile-drawer-divider" />
                  <button type="button" className="tns-mobile-logout-btn" onClick={logout}>
                    Log out
                  </button>
                </>
              )}
            </div>
          </div>
        ) : null}

        {logoutError ? <p className="form-error page-width" role="alert">{logoutError}</p> : null}
      </header>

      {isHome && activePopover ? <div className="tns-home-search-backdrop" aria-hidden="true" /> : null}

      <nav className="tns-mobile-bottom-bar" aria-label="Mobile Navigation">
        <NavLink to="/" className={({ isActive }) => `tns-bottom-tab ${isActive ? "active" : ""}`}>
          <span className="tns-tab-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
            </svg>
          </span>
          <span className="tns-tab-label">Home</span>
        </NavLink>
        <NavLink to="/catalogue" className={({ isActive }) => `tns-bottom-tab ${isActive ? "active" : ""}`}>
          <span className="tns-tab-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
            </svg>
          </span>
          <span className="tns-tab-label">Explore</span>
        </NavLink>
        <NavLink to={user ? "/applications" : "/auth"} className={({ isActive }) => `tns-bottom-tab ${isActive ? "active" : ""}`}>
          <span className="tns-tab-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
            </svg>
          </span>
          <span className="tns-tab-label">Saved</span>
        </NavLink>
        <NavLink to={user ? "/dashboard" : "/auth"} className={({ isActive }) => `tns-bottom-tab ${isActive ? "active" : ""}`}>
          <span className="tns-tab-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M3 3v18h18" />
              <path d="m19 9-5 5-4-4-3 3" />
            </svg>
          </span>
          <span className="tns-tab-label">Track</span>
        </NavLink>
        <NavLink to={user ? "/profile" : "/auth"} className={({ isActive }) => `tns-bottom-tab ${isActive ? "active" : ""}`}>
          <span className="tns-tab-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </span>
          <span className="tns-tab-label">Profile</span>
        </NavLink>
      </nav>
    </>
  );
}

function AuthPage() {
  const { user, isRestoring } = useAuth();
  if (!isRestoring && user) {
    return <Navigate replace to="/dashboard" />;
  }
  return (
    <main className="auth-layout page-width">
      <section>
        <p className="eyebrow">The Next Scholar</p>
        <h1>Keep your opportunities, profile, and next steps in one place.</h1>
        <p className="lead">
          AI-powered scholarship discovery, matching, and verified application tracking at thenextscholar.com.
        </p>
      </section>
      <AuthForm />
    </main>
  );
}

function Dashboard() {
  const { user, isRestoring } = useAuth();
  if (!isRestoring && !user) {
    return <Navigate replace to="/auth" />;
  }
  if (!user) {
    return (
      <main className="page-width loading-page" aria-live="polite">
        Restoring your secure session...
      </main>
    );
  }
  return (
    <main className="workspace-page page-width">
      <section className="workspace-intro">
        <p className="eyebrow">The Next Scholar Workspace</p>
        <h1>Good to see you, {user.email.split("@")[0]}.</h1>
        <p>
          Your secure workspace brings discovery, preparation, and careful source curation into one
          place.
        </p>
      </section>
      <EmailVerificationNotice />
      <div className="workspace-grid">
        <NavLink className="workspace-card" to="/catalogue">
          <span>Explore</span>
          <h2>Verified scholarships</h2>
          <p>Search reviewed, currently open scholarships.</p>
        </NavLink>
        <NavLink className="workspace-card" to="/profile">
          <span>Prepare</span>
          <h2>Profile and fit</h2>
          <p>Build your profile, inspect matches, and track next steps.</p>
        </NavLink>
        <NavLink className="workspace-card" to="/matches">
          <span>Understand</span>
          <h2>Explainable matches</h2>
          <p>See the evidence behind every fit signal.</p>
        </NavLink>
        <NavLink className="workspace-card" to="/applications">
          <span>Act</span>
          <h2>Application command centre</h2>
          <p>Manage source-linked tasks, reminders, and application milestones.</p>
        </NavLink>
        {user.role === "admin" ? (
          <NavLink className="workspace-card" to="/admin">
            <span>Curate</span>
            <h2>Review workspace</h2>
            <p>Resolve review work, inspect quality signals, and safely import records.</p>
          </NavLink>
        ) : null}
      </div>
    </main>
  );
}

function AppRoutes() {
  const location = useLocation();
  const [routeSettling, setRouteSettling] = useState(false);

  useEffect(() => {
    setRouteSettling(true);
    const routeTimer = window.setTimeout(() => setRouteSettling(false), 220);
    return () => window.clearTimeout(routeTimer);
  }, [location.pathname]);

  return (
    <>
      <Topbar />
      <Suspense fallback={<div className="tns-top-loading-bar" aria-live="polite" />}>
        <div className={`tns-route-stage ${routeSettling ? "tns-route-stage--settling" : ""}`}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route path="/auth/password-reset" element={<PasswordResetPage />} />
            <Route path="/verify-email" element={<EmailVerificationPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/catalogue" element={<CataloguePage />} />
            <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/matches" element={<MatchesPage />} />
            <Route path="/tracker" element={<Navigate replace to="/applications" />} />
            <Route path="/applications" element={<CommandCentrePage />} />
            <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
            <Route path="/assistant" element={<AssistantPage />} />
            <Route path="/document-lab" element={<DocumentLabPage />} />
            <Route path="/community" element={<CommunityPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/admin/security" element={<AdminSecurityPage />} />
            <Route path="*" element={<Navigate replace to="/" />} />
          </Routes>
        </div>
      </Suspense>
    </>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
