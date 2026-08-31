import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock("./auth/AuthProvider", () => ({
  AuthForm: () => null,
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: auth.useAuth,
}));

import { Dashboard, Topbar } from "./App";

describe("MVP product navigation", () => {
  beforeEach(() => {
    auth.useAuth.mockReturnValue({
      user: {
        id: "student-1",
        email: "student@example.com",
        role: "student",
        email_verified_at: "2026-08-30T00:00:00Z",
      },
      isRestoring: false,
      sessionError: null,
      signOut: vi.fn(),
    });
  });

  afterEach(cleanup);

  it("does not expose disabled Assistant, Documents, or Community links", () => {
    render(
      <BrowserRouter>
        <Topbar />
      </BrowserRouter>,
    );

    expect(screen.getByRole("link", { name: "Scholarships" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Applications" })).toBeInTheDocument();
    expect(screen.queryByText("Assistant", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Documents", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Community", { exact: true })).not.toBeInTheDocument();
  });

  it("does not place disabled features in the student dashboard", () => {
    render(
      <BrowserRouter>
        <Dashboard />
      </BrowserRouter>,
    );

    expect(screen.getByRole("heading", { name: "Verified scholarships" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Profile and fit" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Explainable matches" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Application command centre" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Scholarship AI" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Documents" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Scholarship community" })).not.toBeInTheDocument();
  });
});
