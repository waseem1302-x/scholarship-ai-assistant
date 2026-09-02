import { createContext, type FormEvent, type ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { ApiError, apiClient, type User } from "../api/client";

type AuthMode = "login" | "register";

interface AuthContextValue {
  user: User | null;
  isRestoring: boolean;
  sessionError: string | null;
  signIn: (
    mode: AuthMode,
    email: string,
    password: string,
    invitationCode?: string,
    acceptBetaTerms?: boolean,
  ) => Promise<void>;
  signInWithGoogle: (idToken: string) => Promise<void>;
  signInWithFacebook: (accessToken: string) => Promise<void>;
  signOut: () => Promise<void>;
  clearRevokedSession: () => void;
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const sessionGeneration = useRef(0);

  useEffect(() => {
    let mounted = true;
    const generation = sessionGeneration.current;
    void apiClient
      .restoreSession()
      .then((restoredUser) => {
        if (mounted && generation === sessionGeneration.current) {
          setUser(restoredUser);
          setSessionError(null);
        }
      })
      .catch((error: unknown) => {
        if (mounted && generation === sessionGeneration.current) {
          setSessionError(
            error instanceof ApiError && error.status >= 500
              ? "We could not restore your session because the service is temporarily unavailable."
              : "We could not restore your session. Check your connection and try again.",
          );
        }
      })
      .finally(() => {
        if (mounted && generation === sessionGeneration.current) {
          setIsRestoring(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isRestoring,
      sessionError,
      async signIn(mode, email, password, invitationCode, acceptBetaTerms) {
        sessionGeneration.current += 1;
        const result = await apiClient.signIn(
          mode,
          email,
          password,
          invitationCode,
          acceptBetaTerms,
        );
        setUser(result.user);
        setSessionError(null);
        setIsRestoring(false);
      },
      async signInWithGoogle(idToken) {
        sessionGeneration.current += 1;
        const result = await apiClient.signInWithGoogle(idToken);
        setUser(result.user);
        setSessionError(null);
        setIsRestoring(false);
      },
      async signInWithFacebook(accessToken) {
        sessionGeneration.current += 1;
        const result = await apiClient.signInWithFacebook(accessToken);
        setUser(result.user);
        setSessionError(null);
        setIsRestoring(false);
      },
      async signOut() {
        await apiClient.signOut();
        sessionGeneration.current += 1;
        setUser(null);
        setSessionError(null);
        setIsRestoring(false);
      },
      clearRevokedSession() {
        sessionGeneration.current += 1;
        apiClient.setAccessToken(null);
        setUser(null);
        setSessionError(null);
        setIsRestoring(false);
      },
      updateUser(nextUser) {
        setUser(nextUser);
      },
    }),
    [isRestoring, sessionError, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return value;
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.24v3.15C3.26 21.36 7.33 24 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.24C.45 8.16 0 9.94 0 12s.45 3.84 1.24 5.42l4.04-3.15z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.24 6.58l4.04 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
      />
    </svg>
  );
}

function FacebookIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
    </svg>
  );
}

export function AuthForm() {
  const { signIn } = useAuth();
  const location = useLocation();
  const routeMode: AuthMode = location.pathname === "/register" ? "register" : "login";
  const [mode, setMode] = useState<AuthMode>(routeMode);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMode(routeMode);
    setError(null);
  }, [routeMode]);

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode);
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError(null);
    setIsSubmitting(true);
    try {
      await signIn(
        mode,
        String(data.get("email")),
        String(data.get("password")),
        String(data.get("invitationCode") || "").trim() || undefined,
        data.get("acceptBetaTerms") === "on",
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to continue.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleGoogleLogin() {
    setError(null);
    setIsSubmitting(true);
    try {
      // If Google GIS client is loaded in window
      if (
        typeof window !== "undefined" &&
        (window as unknown as { google?: { accounts?: { id?: { prompt: () => void } } } }).google
          ?.accounts?.id
      ) {
        (window as unknown as { google: { accounts: { id: { prompt: () => void } } } }).google.accounts.id.prompt();
      } else {
        throw new Error(
          "Google Sign-In is unavailable or not configured. Please use email and password.",
        );
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Google authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleFacebookLogin() {
    setError(null);
    setIsSubmitting(true);
    try {
      throw new Error(
        "Facebook Sign-In is unavailable or not configured. Please use email and password.",
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Facebook authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="auth-card" onSubmit={submit} aria-describedby={error ? "auth-error" : undefined}>
      <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
        <button
          className={mode === "login" ? "is-active" : ""}
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          onClick={() => switchMode("login")}
        >
          Sign in
        </button>
        <button
          className={mode === "register" ? "is-active" : ""}
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          onClick={() => switchMode("register")}
        >
          Create account
        </button>
      </div>

      {/* 1-Click Social Logins */}
      <div className="social-auth-container">
        <button
          className="social-button social-button-google"
          type="button"
          onClick={() => void handleGoogleLogin()}
          disabled={isSubmitting}
        >
          <GoogleIcon />
          <span>Continue with Google</span>
        </button>
        <button
          className="social-button social-button-facebook"
          type="button"
          onClick={() => void handleFacebookLogin()}
          disabled={isSubmitting}
        >
          <FacebookIcon />
          <span>Continue with Facebook</span>
        </button>
      </div>

      <div className="auth-divider">
        <span>or continue with email</span>
      </div>

      <label>
        Email address
        <input name="email" type="email" autoComplete="email" required />
      </label>
      <label>
        Password
        <input
          name="password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          minLength={12}
          required
        />
        {mode === "register" ? <small>Use at least 12 characters.</small> : null}
      </label>
      {mode === "register" ? (
        <>
          <label>
            Beta invitation code
            <input
              name="invitationCode"
              autoComplete="one-time-code"
              minLength={32}
              placeholder="Required when beta invitations are enabled"
            />
            <small>Use the code sent to the email address you entered. Never share it.</small>
          </label>
          <label className="toggle-label">
            <input name="acceptBetaTerms" type="checkbox" />
            I accept the beta terms and privacy notice shown with my invitation.
          </label>
        </>
      ) : null}
      {error ? (
        <p className="form-error" id="auth-error" role="alert">
          {error}
        </p>
      ) : null}
      <button className="button button-primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
      </button>
      {mode === "login" ? <Link className="auth-link" to="/auth/password-reset">Forgot your password?</Link> : null}
    </form>
  );
}
