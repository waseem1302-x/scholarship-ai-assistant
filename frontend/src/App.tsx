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
const AdminReviewPage = lazy(() => import("./features/admin/AdminReviewPage").then((module) => ({ default: module.AdminReviewPage })));
const AdminAcquiredReviewPage = lazy(() => import("./features/admin/AdminAcquiredReviewPage").then((module) => ({ default: module.AdminAcquiredReviewPage })));
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
    <NavLink className="brand" to="/" aria-label="Source-backed Scholarship Assistant home">
      <span aria-hidden="true" className="brand-mark">
        S/
      </span>
      <span>
        <strong>Scholarship Assistant</strong>
        <small>Source-backed guidance</small>
      </span>
    </NavLink>
  );
}

function Topbar() {
  const { user, isRestoring, sessionError, signOut } = useAuth();
  const navigate = useNavigate();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  async function logout() {
    setLogoutError(null);
    setIsSigningOut(true);
    try {
      await signOut();
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
        <div className="product-nav" aria-label="Product navigation">
          <NavLink className="product-nav-link" to="/catalogue">
            Scholarships
          </NavLink>
          {user ? (
            <>
              <NavLink className="product-nav-link" to="/dashboard">
                Dashboard
              </NavLink>
              <NavLink className="product-nav-link" to="/applications">
                Applications
              </NavLink>
              <NavLink className="product-nav-link" to="/assistant">
                Assistant
              </NavLink>
              <details className="product-nav-more">
                <summary>More</summary>
                <div className="product-nav-menu workspace-menu">
                  <div className="workspace-menu-section">
                    <span>Plan</span>
                    <NavLink className="workspace-menu-link" to="/profile">
                      <strong>Profile</strong>
                      <small>Student passport and preferences</small>
                    </NavLink>
                    <NavLink className="workspace-menu-link" to="/matches">
                      <strong>Matches</strong>
                      <small>Eligibility signals and fit checks</small>
                    </NavLink>
                  </div>
                  <div className="workspace-menu-section">
                    <span>Prepare</span>
                    <NavLink className="workspace-menu-link" to="/document-lab">
                      <strong>Documents</strong>
                      <small>Draft review and application materials</small>
                    </NavLink>
                    <NavLink className="workspace-menu-link" to="/community">
                      <strong>Community</strong>
                      <small>Practical scholarship experience</small>
                    </NavLink>
                  </div>
                  {user.role === "admin" ? (
                    <div className="workspace-menu-section workspace-menu-admin">
                      <span>Admin</span>
                      <NavLink className="workspace-menu-link" to="/admin">
                        <strong>Review workspace</strong>
                        <small>Curate records and quality signals</small>
                      </NavLink>
                      <NavLink className="workspace-menu-link" to="/admin/security">
                        <strong>Security</strong>
                        <small>Audit and operational controls</small>
                      </NavLink>
                    </div>
                  ) : null}
                </div>
              </details>
            </>
          ) : null}
        </div>
        <div className="topbar-actions">
          {user ? (
            <button className="button button-quiet" type="button" onClick={logout} disabled={isSigningOut}>
              {isSigningOut ? "Signing out..." : "Sign out"}
            </button>
          ) : (
            <NavLink className="button button-quiet" to="/auth">
              {isRestoring ? "Preparing..." : "Sign in"}
            </NavLink>
          )}
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
        <NavLink className="workspace-card" to="/assistant">
          <span>Research</span>
          <h2>Scholarship AI</h2>
          <p>Ask questions grounded in verified official sources.</p>
        </NavLink>
        <NavLink className="workspace-card" to="/document-lab">
          <span>Improve</span>
          <h2>Documents</h2>
          <p>Get consent-gated editorial feedback on private drafts.</p>
        </NavLink>
        <NavLink className="workspace-card" to="/community">
          <span>Connect</span>
          <h2>Scholarship community</h2>
          <p>Share practical experience while keeping private work private.</p>
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
          <Route path="/admin/review/:opportunityId" element={<AdminReviewPage />} />
          <Route path="/admin/acquired/:candidateId" element={<AdminAcquiredReviewPage />} />
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
