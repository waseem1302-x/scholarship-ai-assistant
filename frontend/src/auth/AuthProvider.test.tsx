import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  restoreSession: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("../api/client", () => ({ apiClient: apiMocks }));

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
  const { user: currentUser, signOut } = useAuth();
  return (
    <>
      <p>{currentUser?.email ?? "signed out"}</p>
      <button type="button" onClick={() => void signOut().catch(() => undefined)}>
        Sign out
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
});
