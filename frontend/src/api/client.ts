export type UserRole = "student" | "admin";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  email_verified_at: string | null;
  created_at: string;
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
  user: User;
}

interface AdminStepUpResponse {
  step_up_token: string;
  expires_at: string;
}

interface ApiErrorBody {
  detail?: unknown;
  error?: { details?: unknown; message?: string };
  message?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function readCsrfToken(cookie = document.cookie): string | undefined {
  return cookie
    .split("; ")
    .find((item) => item.startsWith("csrf_token="))
    ?.split("=")[1];
}

function errorMessage(body: ApiErrorBody | null, status: number): string {
  const detail = body?.error?.details ?? body?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => String(item.message ?? item.msg ?? item)).join("; ");
  }
  if (typeof detail === "string") {
    return detail;
  }
  return body?.error?.message ?? body?.message ?? `Request failed with ${status}.`;
}

export class ApiClient {
  private accessToken: string | null = null;
  private refreshPromise: Promise<TokenResponse | null> | null = null;

  setAccessToken(accessToken: string | null): void {
    this.accessToken = accessToken;
  }

  async signIn(mode: "login" | "register", email: string, password: string): Promise<TokenResponse> {
    const result = await this.request<TokenResponse>(`/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    this.setAccessToken(result.access_token);
    return result;
  }

  async currentUser(): Promise<User> {
    return this.request<User>("/auth/me");
  }

  async restoreSession(): Promise<User | null> {
    const refreshed = await this.refresh();
    if (!refreshed) {
      return null;
    }
    return refreshed.user;
  }

  async signOut(): Promise<void> {
    try {
      await this.request<void>("/auth/logout", { method: "POST" });
    } finally {
      this.setAccessToken(null);
    }
  }

  async adminStepUp(password: string): Promise<AdminStepUpResponse> {
    return this.request<AdminStepUpResponse>("/auth/admin/step-up", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
  }

  async request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }
    if (options.method && options.method !== "GET") {
      const csrfToken = readCsrfToken();
      if (csrfToken) {
        headers.set("X-CSRF-Token", decodeURIComponent(csrfToken));
      }
    }

    const response = await fetch(`/api/v1${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
    });

    if (response.status === 401 && retry && !path.startsWith("/auth/")) {
      const refreshed = await this.refresh();
      if (refreshed) {
        return this.request<T>(path, options, false);
      }
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const text = await response.text();
    let body: T | ApiErrorBody | null = null;
    if (text) {
      try {
        body = JSON.parse(text) as T | ApiErrorBody;
      } catch {
        throw new ApiError(`Request returned an invalid response (${response.status}).`, response.status);
      }
    }
    if (!response.ok) {
      throw new ApiError(errorMessage(body as ApiErrorBody | null, response.status), response.status);
    }
    return body as T;
  }

  private async refresh(): Promise<TokenResponse | null> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.refreshRequest().finally(() => {
        this.refreshPromise = null;
      });
    }
    return this.refreshPromise;
  }

  private async refreshRequest(): Promise<TokenResponse | null> {
    try {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...(readCsrfToken() ? { "X-CSRF-Token": decodeURIComponent(readCsrfToken()!) } : {}),
        },
        body: JSON.stringify({}),
        credentials: "same-origin",
      });
      if (!response.ok) {
        this.setAccessToken(null);
        return null;
      }
      const result = (await response.json()) as TokenResponse;
      this.setAccessToken(result.access_token);
      return result;
    } catch {
      this.setAccessToken(null);
      return null;
    }
  }
}

export const apiClient = new ApiClient();
