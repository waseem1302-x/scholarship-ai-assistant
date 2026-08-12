import { createContext, type FormEvent, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { apiClient, type User } from "../api/client";

type AuthMode = "login" | "register";

interface AuthContextValue {
  user: User | null;
  isRestoring: boolean;
  signIn: (mode: AuthMode, email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);

  useEffect(() => {
    let mounted = true;
    void apiClient.restoreSession().then((restoredUser) => {
      if (mounted) {
        setUser(restoredUser);
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
      async signIn(mode, email, password) {
        const result = await apiClient.signIn(mode, email, password);
        setUser(result.user);
      },
      async signOut() {
        setUser(null);
        await apiClient.signOut();
      },
    }),
    [isRestoring, user],
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

export function AuthForm() {
  const { signIn } = useAuth();
  const [mode, setMode] = useState<AuthMode>("login");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError(null);
    setIsSubmitting(true);
    try {
      await signIn(mode, String(data.get("email")), String(data.get("password")));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to continue.");
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
          onClick={() => setMode("login")}
        >
          Sign in
        </button>
        <button
          className={mode === "register" ? "is-active" : ""}
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          onClick={() => setMode("register")}
        >
          Create account
        </button>
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
      </label>
      {error ? (
        <p className="form-error" id="auth-error" role="alert">
          {error}
        </p>
      ) : null}
      <button className="button button-primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
      </button>
    </form>
  );
}
