import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { useState } from "react";
import { BrowserRouter, MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock("./auth/AuthProvider", () => ({
  AuthForm: () => null,
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: auth.useAuth,
}));

import { Topbar } from "./App";
import { Brand } from "./components/BrandLogo";
import { ScholarshipSearch } from "./components/ScholarshipSearch";
import {
  initialSearch,
  type ActivePopover,
  type HomeSearchState,
} from "./features/home/HomePage";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function SearchHarness({ showLocation = false }: { showLocation?: boolean }) {
  const [search, setSearch] = useState<HomeSearchState>(initialSearch);
  const [activePopover, setActivePopover] = useState<ActivePopover>(null);

  return (
    <>
      <ScholarshipSearch
        search={search}
        activePopover={activePopover}
        onSearchChange={setSearch}
        onPopoverChange={setActivePopover}
      />
      {showLocation ? <LocationProbe /> : null}
    </>
  );
}

describe("premium header and scholarship search", () => {
  afterEach(cleanup);

  it("keeps the signed-out header text-first and secondary to search", () => {
    auth.useAuth.mockReturnValue({ user: null, isRestoring: false, sessionError: null, signOut: vi.fn() });

    render(<BrowserRouter><Topbar /></BrowserRouter>);

    expect(screen.getByRole("link", { name: "Scholarships" })).toBeInTheDocument();
    expect(screen.getByText("How it works")).toBeInTheDocument();
    expect(screen.getByText("For students")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Get Started" })).not.toBeInTheDocument();
    expect(document.querySelector(".tns-home-nav-icon")).not.toBeInTheDocument();
  });

  it("uses task-focused navigation after sign in", () => {
    auth.useAuth.mockReturnValue({
      user: { id: "student-1", email: "scholar@thenextscholar.com", role: "student", email_verified_at: "2026-08-30T00:00:00Z" },
      isRestoring: false,
      sessionError: null,
      signOut: vi.fn(),
    });

    render(<BrowserRouter><Topbar /></BrowserRouter>);

    expect(screen.getByRole("link", { name: "Scholarships" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Matches" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Applications" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Guidance" })).toBeInTheDocument();
  });

  it("uses calm scholarship-search microcopy", () => {
    render(<BrowserRouter><SearchHarness /></BrowserRouter>);

    const desktopSearch = screen.getByRole("search", { name: "Search verified scholarships" });
    const search = within(desktopSearch);

    expect(search.getByText("Where")).toBeInTheDocument();
    expect(search.getByText("Search destinations")).toBeInTheDocument();
    expect(search.getByText("Degree")).toBeInTheDocument();
    expect(search.getByText("Any degree")).toBeInTheDocument();
    expect(search.getByText("Funding")).toBeInTheDocument();
    expect(search.getByText("Any funding")).toBeInTheDocument();
  });

  it("preserves selected filters when routing to the catalogue", () => {
    render(<MemoryRouter initialEntries={["/"]}><SearchHarness showLocation /></MemoryRouter>);

    fireEvent.click(screen.getByText("Search destinations"));
    fireEvent.click(screen.getByRole("button", { name: /^Germany\b/ }));

    const degreeDialog = screen.getByRole("dialog", { name: "Choose degree" });
    fireEvent.click(within(degreeDialog).getByRole("button", { name: /^Master's\b/ }));

    const fundingDialog = screen.getByRole("dialog", { name: "Choose funding" });
    fireEvent.click(within(fundingDialog).getByRole("button", { name: /^Fully Funded\b/ }));

    const desktopSearch = screen.getByRole("search", { name: "Search verified scholarships" });
    fireEvent.click(within(desktopSearch).getByRole("button", { name: "Search scholarships" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/catalogue?country=Germany&degree_level=masters&funding_type=full");
  });

  it("renders the brand mark without the old gradient glow definition", () => {
    render(<BrowserRouter><Brand /></BrowserRouter>);

    expect(document.getElementById("tns-logo-grad")).not.toBeInTheDocument();
    expect(document.getElementById("tns-glow")).not.toBeInTheDocument();
  });
});
