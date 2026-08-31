import { lazy, Suspense, useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";

import { EmailVerificationNotice } from "./auth/AccountLifecycle";
import { AuthForm, AuthProvider, useAuth } from "./auth/AuthProvider";
import { HomePage } from "./features/home/HomePage";

const EmailVerificationPage = lazy(() => import("./auth/AccountLifecycle").then((module) => ({ default: module.EmailVerificationPage })));
const PasswordResetPage = lazy(() => import("./auth/AccountLifecycle").then((module) => ({ default: module.PasswordResetPage })));
const CataloguePage = lazy(() => import("./features/catalogue/CataloguePage").then((module) => ({ default: module.CataloguePage })));
const OpportunityDetailPage = lazy(() => import("./features/catalogue/OpportunityDetailPage").then((module) => ({ default: module.OpportunityDetailPage })));
const AdminPage = lazy(() => import("./features/admin/AdminPage").then((module) => ({ default: module.AdminPage })));
const AdminSecurityPage = lazy(() => import("./features/admin/AdminSecurityPage").then((module) => ({ default: module.AdminSecurityPage })));
const MatchesPage = lazy(() => import("./features/workspace/MatchesPage").then((module) => ({ default: module.MatchesPage })));
const ProfilePage = lazy(() => import("./features/workspace/ProfilePage").then((module) => ({ default: module.ProfilePage })));
const CommandCentrePage = lazy(() => import("./features/workspace/CommandCentrePage").then((module) => ({ default: module.CommandCentrePage })));
const ApplicationDetailPage = lazy(() => import("./features/workspace/ApplicationDetailPage").then((module) => ({ default: module.ApplicationDetailPage })));
const AssistantPage = lazy(() => import("./features/assistant/AssistantPage").then((module) => ({ default: module.AssistantPage })));
const DocumentLabPage = lazy(() => import("./features/document-lab/DocumentLabPage").then((module) => ({ default: module.DocumentLabPage })));
const CommunityPage = lazy(() => import("./features/community/CommunityPage").then((module) => ({ default: module.CommunityPage })));

function Brand() {
  return (
    <NavLink className="brand" to="/" aria-label="Scholarship Assistant home">
      <span aria-hidden="true" className="brand-mark">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <path d="M16 1C7.716 1 1 7.716 1 16c0 4.144 1.68 7.896 4.394 10.606A14.933 14.933 0 0 0 16 31c4.144 0 7.896-1.68 10.606-4.394A14.933 14.933 0 0 0 31 16C31 7.716 24.284 1 16 1zm0 4c2.87 0 5.23 2.1 5.92 5.15-1.84.45-3.8 1.15-5.92 2.1-2.12-.95-4.08-1.65-5.92-2.1C10.77 7.1 13.13 5 16 5zm0 18.5c-3.5 0-6.5-2.5-7.5-6 2.3.6 4.7 1.4 7.5 2.5 2.8-1.1 5.2-1.9 7.5-2.5-1 3.5-4 6-7.5 6z"/>
        </svg>
      </span>
      <span className="brand-text">
        <strong>scholarship stay</strong>
        <small>Verified funding & stays</small>
      </span>
    </NavLink>
  );
}

export function Topbar() {
  const { user, isRestoring, sessionError, signOut } = useAuth();
  const navigate = useNavigate();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  async function logout() {
    setLogoutError(null);
    setIsSigningOut(true);
    try {
      await signOut();
      setMenuOpen(false);
      navigate("/");
    } catch {
      setLogoutError(
        "We could not confirm server sign-out. You are still signed in; please try again.",
      );
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <header className="topbar-shell">
      <nav className="topbar page-width" aria-label="Primary navigation">
        <Brand />

        {/* Center Tabs — Airbnb Style */}
        <div className="product-nav" aria-label="Product navigation">
          <NavLink className="product-nav-link" to="/catalogue">
            <span aria-hidden="true">🌐</span>
            Scholarships
          </NavLink>
          {user ? (
            <>
              <NavLink className="product-nav-link" to="/dashboard">
                <span aria-hidden="true">🏠</span>
                Dashboard
              </NavLink>
              <NavLink className="product-nav-link" to="/applications">
                <span aria-hidden="true">🧳</span>
                Applications
              </NavLink>
            </>
          ) : (
            <>
              <NavLink className="product-nav-link" to="/catalogue?funding_type=full">
                <span aria-hidden="true">🏆</span>
                Full-Ride
              </NavLink>
              <NavLink className="product-nav-link" to="/catalogue?degree_level=bachelors">
                <span aria-hidden="true">🎓</span>
                Bachelor
              </NavLink>
            </>
          )}
        </div>

        {/* Right Actions — Airbnb Style */}
        <div className="topbar-actions">
          <NavLink className="topbar-host-link" to={user ? "/dashboard" : "/auth"}>
            {user ? "Switch to workspace" : "Become an applicant"}
          </NavLink>

          <button
            className="topbar-globe-btn"
            type="button"
            aria-label="Language & Currency"
            title="Language: English (US) · Currency: USD ($)"
            onClick={() => navigate("/catalogue")}
          >
            <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm5.93 7h-2.5a13.3 13.3 0 0 0-1.04-4.22A6.53 6.53 0 0 1 13.93 7zM8 1.52c.7 1.25 1.25 3.1 1.44 5.48H6.56C6.75 4.62 7.3 2.77 8 1.52zm-3.39 1.26A13.3 13.3 0 0 0 3.57 7H1.07a6.53 6.53 0 0 1 3.54-4.22zm-3.54 5.72h2.5c.19 1.6.57 3.06 1.04 4.22A6.53 6.53 0 0 1 1.07 8.5zm5.49 0h2.88c-.19 2.38-.74 4.23-1.44 5.48-.7-1.25-1.25-3.1-1.44-5.48zm4.87 4.22c.47-1.16.85-2.62 1.04-4.22h2.5a6.53 6.53 0 0 1-3.54 4.22z"/>
            </svg>
          </button>

          {/* User Menu Capsule */}
          <div className="user-menu-wrapper">
            <button
              className="user-menu-pill"
              type="button"
              aria-label="Main user menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
            >
              <svg className="hamburger" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden="true">
                <line x1="4" y1="9" x2="28" y2="9" />
                <line x1="4" y1="16" x2="28" y2="16" />
                <line x1="4" y1="23" x2="28" y2="23" />
              </svg>
              <span className={"user-avatar-circle " + (user ? "has-user" : "")}>
                {user ? user.email.slice(0, 1).toUpperCase() : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
                  </svg>
                )}
              </span>
            </button>

            {menuOpen ? (
              <div className="airbnb-dropdown" role="menu">
                {user ? (
                  <>
                    <NavLink className="airbnb-dropdown-item" to="/dashboard" onClick={() => setMenuOpen(false)} role="menuitem">
                      <strong>Dashboard</strong>
                    </NavLink>
                    <NavLink className="airbnb-dropdown-item" to="/applications" onClick={() => setMenuOpen(false)} role="menuitem">
                      Applications tracker
                    </NavLink>
                    <NavLink className="airbnb-dropdown-item" to="/matches" onClick={() => setMenuOpen(false)} role="menuitem">
                      Explainable matches
                    </NavLink>
                    <NavLink className="airbnb-dropdown-item" to="/profile" onClick={() => setMenuOpen(false)} role="menuitem">
                      Student profile & passport
                    </NavLink>
                    {user.role === "admin" ? (
                      <>
                        <div className="airbnb-dropdown-divider" />
                        <NavLink className="airbnb-dropdown-item" to="/admin" onClick={() => setMenuOpen(false)} role="menuitem">
                          Admin review workspace
                        </NavLink>
                        <NavLink className="airbnb-dropdown-item" to="/admin/security" onClick={() => setMenuOpen(false)} role="menuitem">
                          Admin security & audit
                        </NavLink>
                      </>
                    ) : null}
                    <div className="airbnb-dropdown-divider" />
                    <button
                      className="airbnb-dropdown-item"
                      type="button"
                      onClick={logout}
                      disabled={isSigningOut}
                      role="menuitem"
                    >
                      {isSigningOut ? "Signing out..." : "Log out"}
                    </button>
                  </>
                ) : (
                  <>
                    <NavLink className="airbnb-dropdown-item" to="/auth" onClick={() => setMenuOpen(false)} role="menuitem">
                      <strong>Sign up</strong>
                    </NavLink>
                    <NavLink className="airbnb-dropdown-item" to="/auth" onClick={() => setMenuOpen(false)} role="menuitem">
                      Log in
                    </NavLink>
                    <div className="airbnb-dropdown-divider" />
                    <NavLink className="airbnb-dropdown-item" to="/catalogue" onClick={() => setMenuOpen(false)} role="menuitem">
                      Browse all scholarships
                    </NavLink>
                  </>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </nav>
      {logoutError ? <p className="form-error page-width" role="alert">{logoutError}</p> : null}
      {sessionError ? <p className="form-error page-width" role="alert">{sessionError}</p> : null}
    </header>
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
        <p className="eyebrow">Your private workspace</p>
        <h1>Keep your opportunities, profile, and next steps in one place.</h1>
        <p className="lead">
          Your session is protected with a short-lived in-memory access token and a secure refresh
          cookie.
        </p>
      </section>
      <AuthForm />
    </main>
  );
}

export function Dashboard() {
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
        <p className="eyebrow">Welcome back</p>
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
  return (
    <>
      <Topbar />
      <Suspense
        fallback={
          <main className="page-width loading-page" aria-live="polite">
            Loading this workspace...
          </main>
        }
      >
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
