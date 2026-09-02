import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock("./auth/AuthProvider", () => ({
  AuthForm: () => <p>Authentication form</p>,
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: auth.useAuth,
}));

vi.mock("./features/home/HomePage", () => ({
  HomePage: () => <main><section id="how-it-works">How it works content</section></main>,
}));
vi.mock("./features/catalogue/CataloguePage", () => ({
  CataloguePage: () => <main>Scholarship catalogue</main>,
}));
vi.mock("./features/catalogue/OpportunityDetailPage", () => ({
  OpportunityDetailPage: () => <main>Scholarship detail</main>,
}));
vi.mock("./features/workspace/CommandCentrePage", () => ({
  CommandCentrePage: ({ initialLifecycle }: { initialLifecycle?: string }) => (
    <main>{initialLifecycle === "saved" ? "Saved scholarships view" : "Applications view"}</main>
  ),
}));

import { App } from "./App";

const student = {
  id: "student-1",
  email: "student@example.com",
  role: "student",
  email_verified_at: "2026-08-30T00:00:00Z",
};

function renderRoute(path: string, user: typeof student | null = null) {
  window.history.pushState({}, "", path);
  auth.useAuth.mockReturnValue({ user, isRestoring: false, sessionError: null, signOut: vi.fn() });
  return render(<App />);
}

afterEach(() => {
  cleanup();
  window.history.pushState({}, "", "/");
  vi.clearAllMocks();
});

describe("MVP navigation routes", () => {
  it("serves the scholarship catalogue from the product route", async () => {
    renderRoute("/scholarships");
    expect(await screen.findByText("Scholarship catalogue")).toBeInTheDocument();
  });

  it("serves scholarship details from the singular product route", async () => {
    renderRoute("/scholarship/opportunity-1");
    expect(await screen.findByText("Scholarship detail")).toBeInTheDocument();
  });

  it("keeps matches discoverable before login", async () => {
    renderRoute("/matches");
    expect(await screen.findByRole("heading", { name: "Find scholarships that fit your profile." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create your profile" })).toHaveAttribute("href", "/register");
  });

  it("opens the saved application view for authenticated students", async () => {
    renderRoute("/saved", student);
    expect(await screen.findByText("Saved scholarships view")).toBeInTheDocument();
  });

  it("maps the how-it-works route to the existing homepage section", async () => {
    renderRoute("/how-it-works");
    await waitFor(() => {
      expect(window.location.pathname).toBe("/");
      expect(window.location.hash).toBe("#how-it-works");
    });
  });
});
