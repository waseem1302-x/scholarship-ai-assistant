import { lazy, Suspense, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { BrowserRouter } from "react-router-dom";

import { AuthForm, AuthProvider, useAuth } from "./auth/AuthProvider";
import { EmailVerificationNotice } from "./auth/AccountLifecycle";

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
            Catalogue
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
                <div className="product-nav-menu">
                  <NavLink className="product-nav-link" to="/profile">Profile</NavLink>
                  <NavLink className="product-nav-link" to="/matches">Matches</NavLink>
                  <NavLink className="product-nav-link" to="/document-lab">Document Lab</NavLink>
                  <NavLink className="product-nav-link" to="/community">Community</NavLink>
                  {user.role === "admin" ? <>
                  <NavLink className="product-nav-link" to="/admin">
                    Admin
                  </NavLink>
                  <NavLink className="product-nav-link" to="/admin/security">
                    Security
                  </NavLink>
                  </> : null}
                </div>
              </details>
            </>
          ) : null}
        </div>
        <div className="topbar-actions">
          <a className="text-link" href="/docs" target="_blank" rel="noreferrer">
            API documentation
          </a>
          {user ? (
            <button className="button button-quiet" type="button" onClick={logout} disabled={isSigningOut}>
              {isSigningOut ? "Signing out…" : "Sign out"}
            </button>
          ) : (
            <NavLink className="button button-quiet" to="/auth">
              {isRestoring ? "Preparing…" : "Sign in"}
            </NavLink>
          )}
        </div>
      </nav>
      {logoutError ? <p className="form-error page-width" role="alert">{logoutError}</p> : null}
      {sessionError ? <p className="form-error page-width" role="alert">{sessionError}</p> : null}
    </header>
  );
}

function HomePage() {
  const { user, isRestoring } = useAuth();

  return (
    <main>
      <section className="hero page-width">
        <div className="hero-copy">
          <p className="eyebrow">Source-first scholarship intelligence</p>
          <h1>Make your next scholarship decision with confidence.</h1>
          <p className="lead">
            Discover verified opportunities, understand the evidence behind them, and keep your
            application work moving—without unsupported promises.
          </p>
          <div className="hero-actions">
            <NavLink className="button button-primary" to="/catalogue">
              Browse scholarships
            </NavLink>
            <NavLink className="button button-quiet" to={user ? "/dashboard" : "/auth"}>
              {isRestoring ? "Preparing your workspace…" : user ? "Open workspace" : "Get started"}
            </NavLink>
            <a className="button button-quiet" href="#how-it-works">
              How it works
            </a>
          </div>
          <p className="disclaimer">
            Decision support only. This platform does not guarantee admission, scholarship
            selection, or visa approval.
          </p>
        </div>
        <aside className="evidence-card" aria-label="Our evidence standard">
          <span className="card-kicker">The evidence standard</span>
          <h2>Useful only when it is traceable.</h2>
          <ul>
            <li>Official sources are shown alongside each opportunity.</li>
            <li>Changed sources return to review before public visibility.</li>
            <li>Eligibility signals explain what is known, missing, or uncertain.</li>
          </ul>
        </aside>
      </section>

      <section className="trust-strip" id="how-it-works">
        <div className="page-width trust-grid">
          <article>
            <span>01</span>
            <h2>Discover</h2>
            <p>Explore opportunities from reviewed official sources.</p>
          </article>
          <article>
            <span>02</span>
            <h2>Understand</h2>
            <p>See funding, requirements, deadlines, and source evidence in context.</p>
          </article>
          <article>
            <span>03</span>
            <h2>Act</h2>
            <p>Build your profile, compare your fit, and track the application work ahead.</p>
          </article>
        </div>
      </section>
    </main>
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
        <p className="lead">Your session is protected with a short-lived in-memory access token and a secure refresh cookie.</p>
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
    return <main className="page-width loading-page" aria-live="polite">Restoring your secure session…</main>;
  }
  return (
    <main className="workspace-page page-width">
      <section className="workspace-intro">
        <p className="eyebrow">Welcome back</p>
        <h1>Good to see you, {user.email.split("@")[0]}.</h1>
          <p>Your secure workspace brings discovery, preparation, and careful source curation into one place.</p>
      </section>
      <EmailVerificationNotice />
      <div className="workspace-grid">
        <NavLink className="workspace-card" to="/catalogue">
          <span>Explore</span>
          <h2>Verified catalogue</h2>
          <p>Search the reviewed, currently open catalogue.</p>
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
          <h2>Citation-first assistant</h2>
          <p>Ask questions grounded in verified official sources.</p>
        </NavLink>
        <NavLink className="workspace-card" to="/document-lab">
          <span>Improve</span>
          <h2>Private Document Lab</h2>
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
      <Suspense fallback={<main className="page-width loading-page" aria-live="polite">Loading this workspace…</main>}>
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
