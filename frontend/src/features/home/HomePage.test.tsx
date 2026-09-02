import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ScholarshipSearch } from "../../components/ScholarshipSearch";
import { initialSearch, type ActivePopover, type HomeSearchState } from "../catalogue/searchOptions";

const authState = vi.hoisted(() => ({
  user: null as { email: string; role: string } | null,
}));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: authState.user, isRestoring: false }),
}));

import { HomePage } from "./HomePage";

function ScholarshipSearchHarness() {
  const [search, setSearch] = useState<HomeSearchState>(initialSearch);
  const [activePopover, setActivePopover] = useState<ActivePopover>(null);

  return (
    <ScholarshipSearch
      search={search}
      mode="expanded"
      activePopover={activePopover}
      onSearchChange={setSearch}
      onPopoverChange={setActivePopover}
    />
  );
}

describe("HomePage - The Next Scholar", () => {
  beforeEach(() => {
    authState.user = null;
  });

  afterEach(cleanup);

  it("renders the hero section with serif headline and crimson accent", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("Find scholarships.")).toBeInTheDocument();
    expect(screen.getByText("Build stronger applications.")).toBeInTheDocument();
    expect(
      screen.getByText(/Discover 50,000\+ verified scholarships worldwide/i),
    ).toBeInTheDocument();
  });

  it("renders the AI-powered matching banner with circular gauges", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("AI POWERED")).toBeInTheDocument();
    expect(screen.getByText(/Not sure which scholarships you qualify for\?/i)).toBeInTheDocument();
    expect(screen.getByText("87%")).toBeInTheDocument();
    expect(screen.getByText("94%")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
  });

  it("renders featured scholarships without personalized match scores before login", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("Featured scholarships")).toBeInTheDocument();
    expect(screen.getByText("DAAD Development-Related Postgraduate Courses")).toBeInTheDocument();
    expect(screen.getByText("Fulbright Foreign Student Program")).toBeInTheDocument();
    expect(screen.getByText("Chevening Scholarships 2025/26")).toBeInTheDocument();
    expect(screen.queryByText("Full Match")).not.toBeInTheDocument();
    expect(screen.queryByText("90% Match")).not.toBeInTheDocument();
    expect(screen.getAllByText("Check eligibility")).toHaveLength(5);
  });

  it("renders personalized featured match scores after login", () => {
    authState.user = {
      email: "student@thenextscholar.com",
      role: "student",
    };

    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("Full Match")).toBeInTheDocument();
    expect(screen.getAllByText("90% Match")).toHaveLength(2);
  });

  it("renders destination cards with landmark silhouettes", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    const destinationSection = screen.getByText("Browse by destination").closest("section");

    expect(destinationSection).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("Germany")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("UK")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("US")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("Canada")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("Australia")).toBeInTheDocument();
  });

  it("renders How It Works 4-step workflow", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("How it works")).toBeInTheDocument();
    expect(screen.getByText("Discover")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Track")).toBeInTheDocument();
    expect(screen.getByText("Prepare")).toBeInTheDocument();
    expect(document.querySelector(".tns-step-number-badge")).not.toBeInTheDocument();
  });

  it("renders Trust bar metrics", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("500+")).toBeInTheDocument();
    expect(screen.getByText("120+")).toBeInTheDocument();
    expect(screen.getByText("Bachelor • Master • PhD")).toBeInTheDocument();
    expect(screen.getByText("Fully Funded")).toBeInTheDocument();
  });

  it("exposes the desktop scholarship search as a search landmark", () => {
    render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    expect(screen.getByRole("search", { name: /search verified scholarships/i })).toBeInTheDocument();
  });

  it("uses native expanded-state controls for each desktop search field", () => {
    render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    const destination = within(search).getByRole("combobox", { name: /search country/i });
    const degree = within(search).getByRole("button", { name: /degree any degree/i });
    const funding = within(search).getByRole("button", { name: /funding any funding/i });

    expect(destination.tagName).toBe("INPUT");
    expect(destination).toHaveAttribute("aria-controls", "desktop-destination-suggestions");
    expect(degree).toHaveAttribute("aria-controls", "degree-popover");
    expect(funding).toHaveAttribute("aria-controls", "funding-popover");
    expect(destination).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps one active selection surface while switching search fields", () => {
    const { container } = render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    const indicator = container.querySelector(".tns-active-segment-indicator");

    expect(indicator).toBeInTheDocument();
    expect(search).toHaveAttribute("data-active-segment", "none");

    fireEvent.focus(within(search).getByRole("combobox", { name: /search country/i }));
    expect(search).toHaveAttribute("data-active-segment", "where");

    fireEvent.click(within(search).getByRole("button", { name: /degree any degree/i }));
    expect(search).toHaveAttribute("data-active-segment", "degree");
    expect(container.querySelector(".tns-active-segment-indicator")).toBe(indicator);
  });

  it("keeps popover shells mounted while exposing only the active dialog", () => {
    const { container } = render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const destinationPopover = container.querySelector("#destination-popover");
    const degreePopover = container.querySelector("#degree-popover");
    const fundingPopover = container.querySelector("#funding-popover");

    expect(destinationPopover).toHaveAttribute("aria-hidden", "true");
    expect(degreePopover).toHaveAttribute("aria-hidden", "true");
    expect(fundingPopover).toHaveAttribute("aria-hidden", "true");

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    fireEvent.focus(within(search).getByRole("combobox", { name: /search country/i }));
    expect(destinationPopover).toHaveAttribute("aria-hidden", "false");
    expect(degreePopover).toHaveAttribute("aria-hidden", "true");

    fireEvent.click(within(search).getByRole("button", { name: /degree any degree/i }));
    expect(destinationPopover).toHaveAttribute("aria-hidden", "true");
    expect(degreePopover).toHaveAttribute("aria-hidden", "false");
    expect(container.querySelector("#destination-popover")).toBe(destinationPopover);
  });

  it("keeps the destination dialog in the shared shell and advances to degree", () => {
    render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    const destination = within(search).getByRole("combobox", { name: /search country/i });
    fireEvent.focus(destination);

    const destinationPopover = screen.getByRole("dialog", { name: /popular scholarship destinations/i });
    expect(destination).toHaveAttribute("aria-expanded", "true");
    expect(destinationPopover).toHaveAttribute("id", "destination-popover");
    expect(search.querySelector(".tns-popover-shell")).toContainElement(destinationPopover);

    fireEvent.click(within(destinationPopover).getByRole("option", { name: /Germany/ }));

    expect(screen.getByRole("button", { name: /degree any degree/i })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog", { name: /choose degree/i })).toBeInTheDocument();
  });

  it("filters destination suggestions and stores the canonical country", () => {
    render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    const countryInput = within(search).getByRole("combobox", { name: /search country/i });

    fireEvent.focus(countryInput);
    fireEvent.change(countryInput, { target: { value: "jap" } });

    const suggestions = screen.getByRole("listbox", { name: /destination suggestions/i });
    expect(within(suggestions).getByRole("option", { name: /Japan/i })).toBeInTheDocument();
    expect(within(suggestions).queryByRole("option", { name: /Germany/i })).not.toBeInTheDocument();

    fireEvent.click(within(suggestions).getByRole("option", { name: /Japan/i }));

    expect(countryInput).toHaveValue("Japan");
    expect(screen.getByRole("button", { name: /degree any degree/i })).toHaveAttribute("aria-expanded", "true");
  });

  it("supports keyboard selection in the destination combobox", () => {
    render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    const countryInput = within(search).getByRole("combobox", { name: /search country/i });

    fireEvent.focus(countryInput);
    fireEvent.change(countryInput, { target: { value: "net" } });
    fireEvent.keyDown(countryInput, { key: "ArrowDown" });
    fireEvent.keyDown(countryInput, { key: "Enter" });

    expect(countryInput).toHaveValue("Netherlands");
  });

  it("clears a typed destination without closing the search", () => {
    render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    const countryInput = within(search).getByRole("combobox", { name: /search country/i });

    fireEvent.focus(countryInput);
    fireEvent.change(countryInput, { target: { value: "Japan" } });
    fireEvent.click(within(search).getByRole("button", { name: /clear destination/i }));

    expect(countryInput).toHaveValue("");
    expect(countryInput).toHaveAttribute("aria-expanded", "true");
  });

  it("shows a complete mobile search sheet with country degree and funding fields", () => {
    render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /start your search/i }));

    const mobileSheet = screen.getByRole("dialog", { name: /scholarship search/i });
    expect(within(mobileSheet).getByText("Where")).toBeInTheDocument();
    expect(within(mobileSheet).getByText("Degree")).toBeInTheDocument();
    expect(within(mobileSheet).getByText("Funding")).toBeInTheDocument();
  });
});
