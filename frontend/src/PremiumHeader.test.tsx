import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock("./auth/AuthProvider", () => ({
  AuthForm: () => null,
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: auth.useAuth,
}));

import { Topbar } from "./App";
import { Brand } from "./components/BrandLogo";
import {
  SearchPill,
  initialSearch,
  type ActivePopover,
  type HomeSearchState,
} from "./features/home/HomePage";

function SearchHarness() {
  const [search, setSearch] = useState<HomeSearchState>(initialSearch);
  const [activePopover, setActivePopover] = useState<ActivePopover>(null);

  return (
    <SearchPill
      search={search}
      activePopover={activePopover}
      onSearchChange={setSearch}
      onPopoverChange={setActivePopover}
    />
  );
}

describe("premium header and scholarship search", () => {
  afterEach(cleanup);

  it("keeps the signed-out header text-first and secondary to search", () => {
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
    expect(document.querySelector(".tns-home-nav-icon")).not.toBeInTheDocument();
  });

  it("uses task-focused navigation after sign in", () => {
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
  });

  it("uses calm scholarship-search microcopy", () => {
    render(
      <BrowserRouter>
        <SearchHarness />
      </BrowserRouter>,
    );

    expect(screen.getByText("Where")).toBeInTheDocument();
    expect(screen.getByText("Search destinations")).toBeInTheDocument();
    expect(screen.getByText("Degree")).toBeInTheDocument();
    expect(screen.getByText("Any degree")).toBeInTheDocument();
    expect(screen.getByText("Funding")).toBeInTheDocument();
    expect(screen.getByText("Any funding")).toBeInTheDocument();
  });

  it("renders the brand mark without the old gradient glow definition", () => {
    render(
      <BrowserRouter>
        <Brand />
      </BrowserRouter>,
    );

    expect(document.getElementById("tns-logo-grad")).not.toBeInTheDocument();
    expect(document.getElementById("tns-glow")).not.toBeInTheDocument();
  });
});
