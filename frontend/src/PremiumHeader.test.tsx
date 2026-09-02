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
} from "./features/catalogue/searchOptions";

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

    const destination = search.getByRole("combobox", { name: "Search country" });
    const degree = search.getByRole("button", { name: "Degree Any degree" });
    const funding = search.getByRole("button", { name: "Funding Any funding" });

    expect(destination).toHaveAttribute("placeholder", "Anywhere");
    expect(search.getByText("Destination")).toBeInTheDocument();
    expect(within(degree).getByText("Degree")).toBeInTheDocument();
    expect(within(degree).getByText("Any degree")).toBeInTheDocument();
    expect(within(funding).getByText("Funding")).toBeInTheDocument();
    expect(within(funding).getByText("Any funding")).toBeInTheDocument();
  });

  it("preserves selected filters when routing to the catalogue", () => {
    render(<MemoryRouter initialEntries={["/"]}><SearchHarness showLocation /></MemoryRouter>);

    const desktopSearch = screen.getByRole("search", { name: "Search verified scholarships" });
    const countryInput = within(desktopSearch).getByRole("combobox", { name: "Search country" });
    fireEvent.focus(countryInput);
    fireEvent.click(screen.getByRole("option", { name: /^Germany\b/ }));

    const degreeDialog = screen.getByRole("dialog", { name: "Choose degree" });
    fireEvent.click(within(degreeDialog).getByRole("button", { name: /^Master's\b/ }));

    const fundingDialog = screen.getByRole("dialog", { name: "Choose funding" });
    fireEvent.click(within(fundingDialog).getByRole("button", { name: /^Fully Funded\b/ }));

    fireEvent.click(within(desktopSearch).getByRole("button", { name: "Search scholarships" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/catalogue?country=Germany&degree_level=masters&funding_type=full");
  });

  it("keeps an unknown typed destination on the search form until a suggestion is selected", () => {
    render(<MemoryRouter initialEntries={["/"]}><SearchHarness showLocation /></MemoryRouter>);

    const search = screen.getByRole("search", { name: "Search verified scholarships" });
    const countryInput = within(search).getByRole("combobox", { name: /search country/i });

    fireEvent.focus(countryInput);
    fireEvent.change(countryInput, { target: { value: "Atlantis" } });
    fireEvent.click(within(search).getByRole("button", { name: "Search scholarships" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Choose a destination from the suggestions");
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
  });

  it("uses the same canonical destination suggestions in the mobile search", () => {
    render(<MemoryRouter initialEntries={["/"]}><SearchHarness showLocation /></MemoryRouter>);

    fireEvent.click(screen.getByRole("button", { name: /start your search/i }));
    const mobileSearch = screen.getByRole("dialog", { name: /scholarship search/i });
    const countryInput = within(mobileSearch).getByRole("combobox", { name: /search country/i });

    fireEvent.change(countryInput, { target: { value: "mal" } });
    const suggestions = within(mobileSearch).getByRole("listbox", { name: /destination suggestions/i });
    fireEvent.click(within(suggestions).getByRole("option", { name: /Malaysia/i }));
    fireEvent.click(within(mobileSearch).getByRole("button", { name: /search scholarships/i }));

    expect(screen.getByTestId("location")).toHaveTextContent("/catalogue?country=Malaysia");
  });

  it("renders the brand mark without the old gradient glow definition", () => {
    render(<BrowserRouter><Brand /></BrowserRouter>);

    expect(document.getElementById("tns-logo-grad")).not.toBeInTheDocument();
    expect(document.getElementById("tns-glow")).not.toBeInTheDocument();
  });
});
