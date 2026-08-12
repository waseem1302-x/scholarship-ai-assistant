import { useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { BrowserRouter } from "react-router-dom";

import { AuthForm, AuthProvider, useAuth } from "./auth/AuthProvider";
import { EmailVerificationNotice, EmailVerificationPage, PasswordResetPage } from "./auth/AccountLifecycle";
import { CataloguePage } from "./features/catalogue/CataloguePage";
import { OpportunityDetailPage } from "./features/catalogue/OpportunityDetailPage";
import { AdminPage } from "./features/admin/AdminPage";
import { MatchesPage } from "./features/workspace/MatchesPage";
import { ProfilePage } from "./features/workspace/ProfilePage";
import { TrackerPage } from "./features/workspace/TrackerPage";

function Brand() {
  return (
    <NavLink className="brand" to="/" aria-label="Scholarship AI Assistant home">
      <span aria-hidden="true" className="brand-mark">
        S/
      </span>
      <span>
        <strong>Scholarship AI</strong>
        <small>Opportunity intelligence</small>
      </span>
    </NavLink>
  );
}

function Topbar() {
  const { user, isRestoring, signOut } = useAuth();
  const navigate = useNavigate();
  const [isSigningOut, setIsSigningOut] = useState(false);

  async function logout() {
    setIsSigningOut(true);
    try {
      await signOut();
      navigate("/");
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
              <NavLink className="product-nav-link" to="/profile">
                Profile
              </NavLink>
              <NavLink className="product-nav-link" to="/matches">
                Matches
              </NavLink>
              <NavLink className="product-nav-link" to="/tracker">
                Tracker
              </NavLink>
              {user.role === "admin" ? (
                <NavLink className="product-nav-link" to="/admin">
                  Admin
                </NavLink>
              ) : null}
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
        <NavLink className="workspace-card" to="/tracker">
          <span>Act</span>
          <h2>Application tracker</h2>
          <p>Keep status, personal deadlines, and notes in one place.</p>
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
        <Route path="/tracker" element={<TrackerPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
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
