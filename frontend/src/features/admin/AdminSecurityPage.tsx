import { type FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";

import { apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";

function base64UrlBytes(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function base64Url(value: ArrayBuffer | null): string | null {
  if (!value) return null;
  const binary = String.fromCharCode(...new Uint8Array(value));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function creationOptions(options: PublicKeyCredentialCreationOptionsJSON): PublicKeyCredentialCreationOptions {
  return {
    ...options,
    challenge: base64UrlBytes(options.challenge),
    user: { ...options.user, id: base64UrlBytes(options.user.id) },
    excludeCredentials: options.excludeCredentials?.map((item) => ({ ...item, id: base64UrlBytes(item.id) })),
  } as PublicKeyCredentialCreationOptions;
}

function requestOptions(options: PublicKeyCredentialRequestOptionsJSON): PublicKeyCredentialRequestOptions {
  return {
    ...options,
    challenge: base64UrlBytes(options.challenge),
    allowCredentials: options.allowCredentials?.map((item) => ({ ...item, id: base64UrlBytes(item.id) })),
  } as PublicKeyCredentialRequestOptions;
}

function serialiseCredential(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAttestationResponse | AuthenticatorAssertionResponse;
  const common = {
    id: credential.id,
    rawId: base64Url(credential.rawId),
    type: credential.type,
    response: { clientDataJSON: base64Url(response.clientDataJSON) },
  };
  if ("attestationObject" in response) {
    return { ...common, response: { ...common.response, attestationObject: base64Url(response.attestationObject) } };
  }
  return {
    ...common,
    response: {
      ...common.response,
      authenticatorData: base64Url(response.authenticatorData),
      signature: base64Url(response.signature),
      userHandle: base64Url(response.userHandle),
    },
  };
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "We could not complete this security action.";
}

export function AdminSecurityPage() {
  const { user, isRestoring } = useAuth();
  const [password, setPassword] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteDays, setInviteDays] = useState(14);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (isRestoring) return <main className="page-width loading-page" aria-live="polite">Restoring your secure session...</main>;
  if (!user) return <Navigate replace to="/auth" />;
  if (user.role !== "admin") return <Navigate replace to="/dashboard" />;
  const supported = typeof window !== "undefined" && "PublicKeyCredential" in window;

  async function registerPasskey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null); setStatus(null);
    try {
      if (!supported) throw new Error("This browser does not support passkeys. Use a current browser on a secure connection.");
      const result = await apiClient.passkeyRegistrationOptions(password);
      const credential = await navigator.credentials.create({ publicKey: creationOptions(result.options as PublicKeyCredentialCreationOptionsJSON) });
      if (!(credential instanceof PublicKeyCredential)) throw new Error("Passkey registration was cancelled.");
      await apiClient.registerPasskey(serialiseCredential(credential));
      setPassword(""); setStatus("Passkey registered. Keep a second approved administrator available for recovery.");
    } catch (requestError) { setError(message(requestError)); } finally { setBusy(false); }
  }

  async function verifyStepUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null); setStatus(null);
    try {
      if (!supported) throw new Error("This browser does not support passkeys. Use a current browser on a secure connection.");
      const result = await apiClient.mfaStepUpOptions(password);
      const credential = await navigator.credentials.get({ publicKey: requestOptions(result.options as PublicKeyCredentialRequestOptionsJSON) });
      if (!(credential instanceof PublicKeyCredential)) throw new Error("Passkey verification was cancelled.");
      const stepUp = await apiClient.completeMfaStepUp(serialiseCredential(credential));
      setPassword(""); setStatus(`MFA step-up is ready until ${new Date(stepUp.expires_at).toLocaleTimeString()}. Use it for one administrator change.`);
    } catch (requestError) { setError(message(requestError)); } finally { setBusy(false); }
  }

  async function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null); setStatus(null); setInviteCode(null);
    try {
      const invitation = await apiClient.createBetaInvitation(inviteEmail, inviteDays, password);
      setPassword(""); setInviteEmail(""); setInviteCode(invitation.invitation_code);
      setStatus(`Invitation created for ${invitation.email}; it expires ${new Date(invitation.expires_at).toLocaleDateString()}.`);
    } catch (requestError) { setError(message(requestError)); } finally { setBusy(false); }
  }

  return <main className="account-page page-width"><section className="account-intro"><p className="eyebrow">Administrator security</p><h1>Protect production changes with a passkey.</h1><p className="lead">Production administrator actions require your current password and a verified passkey. Passwords and passkey data never leave this page except for the secure authentication exchange.</p></section><section className="account-card"><form className="account-section" onSubmit={registerPasskey}><h2>Register this passkey</h2><label>Administrator password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label><button className="button button-primary" disabled={busy || !supported}>{busy ? "Working..." : "Register passkey"}</button></form><form className="account-section" onSubmit={verifyStepUp}><h2>Verify a production step-up</h2><label>Administrator password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label><button className="button button-quiet" disabled={busy || !supported}>{busy ? "Working..." : "Verify passkey"}</button></form><form className="account-section" onSubmit={createInvitation}><h2>Invite one beta participant</h2><p>Use only after the release checklist and approved cohort cap are in place. The code is shown once; deliver it through the participant's verified email channel.</p><label>Participant email<input type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} autoComplete="email" required /></label><label>Invitation validity (days)<input type="number" min="1" max="90" value={inviteDays} onChange={(event) => setInviteDays(Number(event.target.value))} required /></label><label>Administrator password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label><button className="button button-primary" disabled={busy || !supported}>{busy ? "Working..." : "Create invitation with passkey"}</button></form>{inviteCode ? <section className="account-section" aria-live="polite"><h2>Copy this invitation code now</h2><code>{inviteCode}</code><p>This code cannot be retrieved later. Do not place it in a ticket, log, or shared document.</p></section> : null}{!supported ? <p className="form-error" role="alert">Passkeys need a current browser on HTTPS (or localhost during local testing).</p> : null}{error ? <p className="form-error" role="alert">{error}</p> : null}{status ? <p className="form-success" role="status">{status}</p> : null}</section></main>;
}
