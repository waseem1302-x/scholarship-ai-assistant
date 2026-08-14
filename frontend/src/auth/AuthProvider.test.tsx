import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => {
  class ApiError extends Error {
    constructor(message: string, public readonly status: number) {
      super(message);
    }
  }
  return {
    restoreSession: vi.fn(),
    signOut: vi.fn(),
    setAccessToken: vi.fn(),
    ApiError,
  };
});

vi.mock("../api/client", () => ({
  apiClient: apiMocks,
  ApiError: apiMocks.ApiError,
}));

import { AuthProvider, useAuth } from "./AuthProvider";

const user = {
  id: "student-id",
  email: "student@example.com",
  role: "student" as const,
  is_active: true,
  email_verified_at: null,
  created_at: "2099-01-01T00:00:00Z",
};

function SessionProbe() {
  const { user: currentUser, sessionError, signOut, clearRevokedSession } = useAuth();
  return (
    <>
      <p>{currentUser?.email ?? "signed out"}</p>
      {sessionError ? <p role="alert">{sessionError}</p> : null}
      <button type="button" onClick={() => void signOut().catch(() => undefined)}>
        Sign out
      </button>
      <button type="button" onClick={clearRevokedSession}>
        Confirm revoked session
      </button>
    </>
  );
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("AuthProvider logout", () => {
  it("retains the local user if server-session revocation fails", async () => {
    apiMocks.restoreSession.mockResolvedValue(user);
    apiMocks.signOut.mockRejectedValue(new Error("Temporary outage"));
    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>,
    );

    await screen.findByText(user.email);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(apiMocks.signOut).toHaveBeenCalledOnce());
    expect(screen.getByText(user.email)).toBeInTheDocument();
  });

  it("clears the local user after server-session revocation succeeds", async () => {
    apiMocks.restoreSession.mockResolvedValue(user);
    apiMocks.signOut.mockResolvedValue(undefined);
    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>,
    );

    await screen.findByText(user.email);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await screen.findByText("signed out");
  });

  it("clears local state without another logout after server-confirmed revocation", async () => {
    apiMocks.restoreSession.mockResolvedValue(user);
    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>,
    );

    await screen.findByText(user.email);
    fireEvent.click(screen.getByRole("button", { name: "Confirm revoked session" }));

    await screen.findByText("signed out");
    expect(apiMocks.signOut).not.toHaveBeenCalled();
    expect(apiMocks.setAccessToken).toHaveBeenCalledWith(null);
  });
});

describe("AuthProvider session restoration", () => {
  it("shows a temporary-service message rather than reporting an expired session", async () => {
    apiMocks.restoreSession.mockRejectedValue(new apiMocks.ApiError("Unavailable", 503));
    render(
      <AuthProvider>
        <SessionProbe />
      </AuthProvider>,
    );

    expect(
      await screen.findByText(/could not restore your session because the service is temporarily unavailable/i),
    ).toBeInTheDocument();
    expect(screen.getByText("signed out")).toBeInTheDocument();
  });
});