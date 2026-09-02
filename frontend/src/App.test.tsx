import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

    const navigation = within(screen.getByRole("navigation", { name: "Product navigation" }));
    expect(navigation.getByRole("link", { name: "Scholarships" })).toBeInTheDocument();
    expect(navigation.getByRole("link", { name: "How It Works" })).toBeInTheDocument();
    expect(navigation.getByRole("link", { name: "Find Matches" })).toBeInTheDocument();
    const authActions = within(document.querySelector(".tns-auth-actions") as HTMLElement);
    expect(authActions.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(authActions.getByRole("link", { name: "Get Started" })).toBeInTheDocument();
  });

  it("renders the approved two-line scholarship brand", () => {
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

    const brand = screen.getByRole("link", { name: "The Next Scholar home" });
    expect(within(brand).getByText("The Next")).toBeInTheDocument();
    expect(within(brand).getByText("Scholar")).toBeInTheDocument();
    expect(brand.querySelector(".tns-brand-opportunity-accent")).toBeInTheDocument();
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

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    fireEvent.focus(within(search).getByRole("combobox", { name: /search country/i }));
    expect(screen.getByRole("dialog", { name: /popular scholarship destinations/i })).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog", { name: /popular scholarship destinations/i })).not.toBeInTheDocument();
  });

  it("uses separate enter and exit thresholds to prevent scroll-state thrashing", async () => {
    auth.useAuth.mockReturnValue({
      user: null,
      isRestoring: false,
      sessionError: null,
      signOut: vi.fn(),
    });
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0, writable: true });

    render(
      <BrowserRouter>
        <Topbar />
      </BrowserRouter>,
    );

    const header = document.querySelector(".tns-header");

    await act(async () => {
      window.scrollY = 97;
      fireEvent.scroll(window);
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    });
    expect(header).toHaveClass("tns-header--search-compact");

    await act(async () => {
      window.scrollY = 70;
      fireEvent.scroll(window);
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    });
    expect(header).toHaveClass("tns-header--search-compact");

    await act(async () => {
      window.scrollY = 47;
      fireEvent.scroll(window);
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    });
    expect(header).not.toHaveClass("tns-header--search-compact");
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

    const navigation = within(screen.getByRole("navigation", { name: "Product navigation" }));
    expect(navigation.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(navigation.getByRole("link", { name: "Scholarships" })).toBeInTheDocument();
    expect(navigation.getByRole("link", { name: "Matches" })).toBeInTheDocument();
    expect(navigation.getByRole("link", { name: "Applications" })).toBeInTheDocument();
    expect(navigation.queryByRole("link", { name: "Guidance" })).not.toBeInTheDocument();
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
    expect(screen.getByRole("menuitem", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Saved Scholarships" })).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
