import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient, readCsrfToken } from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("readCsrfToken", () => {
  it("returns the CSRF token without persisting sensitive state", () => {
    expect(readCsrfToken("theme=light; csrf_token=secure%2Dvalue; other=1")).toBe("secure%2Dvalue");
  });

  it("returns undefined when the cookie is unavailable", () => {
    expect(readCsrfToken("theme=light")).toBeUndefined();
  });
});

describe("account lifecycle API methods", () => {
  it("uses the existing verification and password-reset contracts", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ accepted: true, expires_at: "2099-01-01T00:00:00Z", debug_token: null }))
      .mockResolvedValueOnce(jsonResponse({ id: "user-id", email: "student@example.com", role: "student", is_active: true, email_verified_at: "2099-01-01T00:00:00Z", created_at: "2099-01-01T00:00:00Z" }))
      .mockResolvedValueOnce(jsonResponse({ accepted: true, expires_at: null, debug_token: null }))
      .mockResolvedValueOnce(jsonResponse({}, 204));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();
    client.setAccessToken("access-token");

    await client.requestEmailVerification();
    await client.confirmEmailVerification("verification-token");
    await client.requestPasswordReset("student@example.com");
    await client.confirmPasswordReset("reset-token", "UpdatedPassword2026");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/email-verifications",
      "/api/v1/auth/email-verifications/confirm",
      "/api/v1/auth/password-resets",
      "/api/v1/auth/password-resets/confirm",
    ]);
    expect(fetchMock.mock.calls[0][1].headers.get("Authorization")).toBe("Bearer access-token");
    expect(fetchMock.mock.calls[1][1].body).toBe(JSON.stringify({ token: "verification-token" }));
    expect(fetchMock.mock.calls[2][1].body).toBe(JSON.stringify({ email: "student@example.com" }));
    expect(fetchMock.mock.calls[3][1].body).toBe(JSON.stringify({ token: "reset-token", new_password: "UpdatedPassword2026" }));
  });
});

describe("logout", () => {
  it("keeps the access token when server-session revocation fails", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ error: { message: "Temporary outage" } }, 503))
      .mockResolvedValueOnce(jsonResponse({ id: "student-id" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();
    client.setAccessToken("access-token");

    await expect(client.signOut()).rejects.toMatchObject({ status: 503 });
    await client.currentUser();

    expect(fetchMock.mock.calls[1][1].headers.get("Authorization")).toBe("Bearer access-token");
  });

  it("clears the access token only after server-session revocation succeeds", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({}, 204))
      .mockResolvedValueOnce(jsonResponse({ id: "student-id" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();
    client.setAccessToken("access-token");

    await client.signOut();
    await client.currentUser();

    expect(fetchMock.mock.calls[1][1].headers.get("Authorization")).toBeNull();
  });
});

describe("refresh", () => {
  it("treats only an invalid refresh credential as an expired session", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ error: { message: "Invalid refresh token" } }, 401))
      .mockResolvedValueOnce(jsonResponse({ id: "student-id" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();
    client.setAccessToken("access-token");

    await expect(client.restoreSession()).resolves.toBeNull();
    await client.currentUser();

    expect(fetchMock.mock.calls[1][1].headers.get("Authorization")).toBeNull();
  });

  it("preserves the session and surfaces a temporary refresh service failure", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ error: { message: "Service unavailable" } }, 503))
      .mockResolvedValueOnce(jsonResponse({ id: "student-id" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();
    client.setAccessToken("access-token");

    await expect(client.restoreSession()).rejects.toMatchObject({ status: 503 });
    await client.currentUser();

    expect(fetchMock.mock.calls[1][1].headers.get("Authorization")).toBe("Bearer access-token");
  });

  it("preserves the session when the refresh request cannot reach the server", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("Network request failed"))
      .mockResolvedValueOnce(jsonResponse({ id: "student-id" }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new ApiClient();
    client.setAccessToken("access-token");

    await expect(client.restoreSession()).rejects.toThrow("Network request failed");
    await client.currentUser();

    expect(fetchMock.mock.calls[1][1].headers.get("Authorization")).toBe("Bearer access-token");
  });
});

describe("administrator MFA fallback", () => {
  it("does not interpret a generic authorization denial as an MFA challenge", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse({ error: { code: "forbidden", message: "Administrator access is required." } }, 403),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(new ApiClient().adminStepUp("password")).rejects.toMatchObject({
      status: 403,
      code: "forbidden",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
