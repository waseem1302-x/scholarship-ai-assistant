import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient, type AccountTokenDelivery, type User } from "../api/client";
import { useAuth } from "./AuthProvider";

function messageFor(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function LocalDevelopmentToken({ delivery, label }: { delivery: AccountTokenDelivery | null; label: string }) {
  if (!delivery?.debug_token) return null;
  return (
    <aside className="development-token" aria-label="Local development token">
      <strong>Local development token</strong>
      <p>This token is available only outside production. It is shown here once and is not stored in the browser.</p>
      <code aria-label={label}>{delivery.debug_token}</code>
    </aside>
  );
}

export function EmailVerificationNotice() {
  const { user } = useAuth();
  if (!user || user.email_verified_at) return null;
  return (
    <aside className="verification-notice">
      <div>
        <strong>Verify your email address</strong>
        <p>Verification protects account recovery and is required for administrator changes in production.</p>
      </div>
      <Link className="button button-quiet" to="/verify-email">Verify email</Link>
    </aside>
  );
}

export function EmailVerificationPage() {
  const { user, isRestoring, updateUser } = useAuth();
  const [searchParams] = useSearchParams();
  const [token, setToken] = useState(searchParams.get("token") ?? "");
  const [delivery, setDelivery] = useState<AccountTokenDelivery | null>(null);
  const [isRequesting, setIsRequesting] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifiedUser, setVerifiedUser] = useState<User | null>(null);

  if (isRestoring) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session...</main>;
  if (user?.email_verified_at || verifiedUser) {
    return (
      <main className="account-page page-width">
        <section className="account-card">
          <p className="eyebrow">Email verification</p>
          <h1>Email address confirmed.</h1>
          <p>Your account can now use verification-dependent features.</p>
          <Link className="button button-primary" to={user ? "/dashboard" : "/auth"}>{user ? "Return to workspace" : "Sign in"}</Link>
        </section>
      </main>
    );
  }

  async function requestVerification() {
    setError(null);
    setIsRequesting(true);
    try {
      const response = await apiClient.requestEmailVerification();
      setDelivery(response);
    } catch (requestError) {
      setError(messageFor(requestError, "Unable to request email verification."));
    } finally {
      setIsRequesting(false);
    }
  }

  async function confirmVerification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsConfirming(true);
    try {
      const verified = await apiClient.confirmEmailVerification(token.trim());
      if (user?.id === verified.id) updateUser(verified);
      setVerifiedUser(verified);
    } catch (requestError) {
      setError(messageFor(requestError, "Unable to confirm this verification token."));
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <main className="account-page page-width">
      <section className="account-intro">
        <p className="eyebrow">Email verification</p>
        <h1>Confirm that this email belongs to you.</h1>
        <p className="lead">Use the verification token from your email. Tokens expire and can only be used once.</p>
      </section>
      <section className="account-card">
        {user ? (
          <div className="account-section">
            <h2>Request a verification token</h2>
            <p>We will send a verification token to <strong>{user.email}</strong>.</p>
            <button className="button button-quiet" type="button" onClick={requestVerification} disabled={isRequesting}>
              {isRequesting ? "Requesting..." : "Send verification email"}
            </button>
            {delivery ? <p className="form-success" role="status">If delivery is configured, a verification email has been requested.</p> : null}
            <LocalDevelopmentToken delivery={delivery} label="Development verification token" />
          </div>
        ) : (
          <p className="account-note">Sign in to request a new verification token. You can still confirm an existing token below.</p>
        )}
        <form className="account-section" onSubmit={confirmVerification} aria-describedby={error ? "verification-error" : undefined}>
          <h2>Confirm your token</h2>
          <label>
            Verification token
            <input name="token" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="one-time-code" minLength={32} required />
          </label>
          {error ? <p className="form-error" id="verification-error" role="alert">{error}</p> : null}
          <button className="button button-primary" type="submit" disabled={isConfirming}>
            {isConfirming ? "Confirming..." : "Verify email"}
          </button>
        </form>
      </section>
    </main>
  );
}

export function PasswordResetPage() {
  const { signOut } = useAuth();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [token, setToken] = useState(searchParams.get("token") ?? "");
  const [newPassword, setNewPassword] = useState("");
  const [delivery, setDelivery] = useState<AccountTokenDelivery | null>(null);
  const [isRequesting, setIsRequesting] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [requested, setRequested] = useState(Boolean(token));
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function requestReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsRequesting(true);
    try {
      const response = await apiClient.requestPasswordReset(email);
      setDelivery(response);
      setRequested(true);
    } catch (requestError) {
      setError(messageFor(requestError, "Unable to request a password reset."));
    } finally {
      setIsRequesting(false);
    }
  }

  async function confirmReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/[A-Za-z]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError("New password must contain at least one letter and one number.");
      return;
    }
    setError(null);
    setIsConfirming(true);
    try {
      await apiClient.confirmPasswordReset(token.trim(), newPassword);
      void signOut().catch(() => undefined);
      setCompleted(true);
    } catch (requestError) {
      setError(messageFor(requestError, "Unable to reset this password."));
    } finally {
      setIsConfirming(false);
    }
  }

  if (completed) {
    return (
      <main className="account-page page-width">
        <section className="account-card">
          <p className="eyebrow">Password reset</p>
          <h1>Password updated.</h1>
          <p>For your security, previous refresh sessions have been signed out. Use your new password to sign in.</p>
          <Link className="button button-primary" to="/auth">Sign in</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="account-page page-width">
      <section className="account-intro">
        <p className="eyebrow">Password reset</p>
        <h1>Regain access without revealing your account.</h1>
        <p className="lead">We use the same response whether or not an address has an account. Reset tokens expire and can only be used once.</p>
      </section>
      <section className="account-card">
        {!requested ? (
          <form className="account-section" onSubmit={requestReset} aria-describedby={error ? "reset-error" : undefined}>
            <h2>Request a reset token</h2>
            <label>
              Email address
              <input name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
            </label>
            {error ? <p className="form-error" id="reset-error" role="alert">{error}</p> : null}
            <button className="button button-primary" type="submit" disabled={isRequesting}>{isRequesting ? "Requesting..." : "Request password reset"}</button>
            <Link className="auth-link" to="/auth">Return to sign in</Link>
          </form>
        ) : (
          <>
            <div className="account-section">
              <h2>Check your email</h2>
              <p className="form-success" role="status">If an active account uses that address, a reset token has been requested.</p>
              <LocalDevelopmentToken delivery={delivery} label="Development password reset token" />
            </div>
            <form className="account-section" onSubmit={confirmReset} aria-describedby={error ? "reset-error" : undefined}>
              <h2>Set a new password</h2>
              <label>
                Reset token
                <input name="token" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="one-time-code" minLength={32} required />
              </label>
              <label>
                New password
                <input name="new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" minLength={12} required />
              </label>
              <p className="account-note">Use at least 12 characters, including a letter and a number.</p>
              {error ? <p className="form-error" id="reset-error" role="alert">{error}</p> : null}
              <button className="button button-primary" type="submit" disabled={isConfirming}>{isConfirming ? "Updating..." : "Update password"}</button>
              <Link className="auth-link" to="/auth">Return to sign in</Link>
            </form>
          </>
        )}
      </section>
    </main>
  );
}
