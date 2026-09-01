import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock("./auth/AuthProvider", () => ({
  AuthForm: () => null,
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: auth.useAuth,
}));

import { Topbar } from "./App";

describe("The Next Scholar Topbar Navigation", () => {
  afterEach(cleanup);

  it("renders calm pre-login navigation before user is logged in", () => {
    auth.useAuth.mockReturnValue({
      user: null,
      isRestoring: false,
      sessionError: null,
      signOut: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Topbar />
      </BrowserRouter>,
    );

    expect(screen.getByRole("link", { name: "Scholarships" })).toBeInTheDocument();
    expect(screen.getByText("How it works")).toBeInTheDocument();
    expect(screen.getByText("For students")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Get Started" })).not.toBeInTheDocument();
  });

  it("keeps the home navigation text-first without decorative emoji icons", () => {
    auth.useAuth.mockReturnValue({
      user: null,
      isRestoring: false,
      sessionError: null,
      signOut: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Topbar />
      </BrowserRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Product navigation" })).toBeInTheDocument();
    expect(document.querySelector(".tns-home-nav-icon")).not.toBeInTheDocument();
  });

  it("closes the homepage search popup when clicking outside", () => {
    auth.useAuth.mockReturnValue({
      user: null,
      isRestoring: false,
      sessionError: null,
      signOut: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Topbar />
      </BrowserRouter>,
    );

    fireEvent.click(screen.getByText("Search destinations"));
    expect(screen.getByRole("dialog", { name: /popular scholarship destinations/i })).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog", { name: /popular scholarship destinations/i })).not.toBeInTheDocument();
  });

  it("renders task-focused navigation after user logs in", () => {
    auth.useAuth.mockReturnValue({
      user: {
        id: "student-1",
        email: "scholar@thenextscholar.com",
        role: "student",
        email_verified_at: "2026-08-30T00:00:00Z",
      },
      isRestoring: false,
      sessionError: null,
      signOut: vi.fn(),
    });

    render(
      <BrowserRouter>
        <Topbar />
      </BrowserRouter>,
    );

    expect(screen.getByRole("link", { name: "Scholarships" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Matches" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Applications" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Guidance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "User account menu" })).toBeInTheDocument();
  });

  it("toggles user menu dropdown and closes on outside click", () => {
    const signOutMock = vi.fn();
    auth.useAuth.mockReturnValue({
      user: {
        id: "student-1",
        email: "scholar@thenextscholar.com",
        role: "student",
        email_verified_at: "2026-08-30T00:00:00Z",
      },
      isRestoring: false,
      sessionError: null,
      signOut: signOutMock,
    });

    render(
      <BrowserRouter>
        <Topbar />
      </BrowserRouter>,
    );

    const userBtn = screen.getByRole("button", { name: "User account menu" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    fireEvent.click(userBtn);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(screen.getByText(/Profile & criteria/i)).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
