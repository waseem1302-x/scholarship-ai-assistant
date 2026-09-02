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

  it("presents profile-based scholarship matching as the primary hero journey", () => {
    const { container } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    const hero = screen.getByRole("region", { name: /find scholarships that fit you/i });

    expect(within(hero).getByText("Find scholarships")).toBeInTheDocument();
    expect(within(hero).getByText("that fit you.")).toBeInTheDocument();
    expect(
      within(hero).getByText(/Create your profile once. We compare it with verified eligibility criteria/i),
    ).toBeInTheDocument();
    expect(within(hero).getByRole("link", { name: /find my matches/i })).toHaveAttribute("href", "/profile");
    expect(within(hero).getByRole("link", { name: /find my matches/i })).toHaveClass("tns-hero-cta--primary");
    expect(within(hero).getByRole("link", { name: /explore scholarships/i })).toHaveAttribute("href", "/scholarships");
    expect(within(hero).getByText("Profile once")).toBeInTheDocument();
    expect(within(hero).getByText("Verified criteria")).toBeInTheDocument();
    expect(within(hero).getByText("Clear reasons")).toBeInTheDocument();
    expect(within(hero).getByText("Your profile")).toBeInTheDocument();
    expect(within(hero).getByText("Strong match")).toBeInTheDocument();
    expect(within(hero).getByText("How it works")).toBeInTheDocument();
    expect(within(hero).getByText("Why it fits")).toBeInTheDocument();
    expect(within(hero).getByText("3 criteria aligned")).toBeInTheDocument();
    expect(container.querySelector(".tns-match-bridge")).not.toHaveTextContent(/criteria aligned/i);
    expect(container.querySelector(".tns-fit-reasons-head")).toHaveTextContent("3 criteria aligned");
    expect(within(hero).getByText("Degree requirement met")).toBeInTheDocument();
    expect(within(hero).getByText("Field aligned")).toBeInTheDocument();
    expect(within(hero).getByText("Open to your nationality")).toBeInTheDocument();
    expect(within(hero).getByRole("heading", { name: "Erasmus Mundus Joint Master" })).toBeInTheDocument();
    expect(within(hero).queryByText("94% Match")).not.toBeInTheDocument();
    expect(within(hero).queryByText("More aligned opportunities")).not.toBeInTheDocument();
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

    expect(screen.getByRole("heading", { name: "How it works" })).toBeInTheDocument();
    expect(screen.getByText("Discover")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Track")).toBeInTheDocument();
    expect(screen.getByText("Prepare")).toBeInTheDocument();
    expect(document.querySelector(".tns-step-number-badge")).not.toBeInTheDocument();
  });

  it("renders Trust bar metrics", () => {
    const { container } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    const trustBar = container.querySelector(".tns-trust-bar-section");

    expect(trustBar).toBeInTheDocument();
    expect(within(trustBar as HTMLElement).getByText("500+")).toBeInTheDocument();
    expect(within(trustBar as HTMLElement).getByText("120+")).toBeInTheDocument();
    expect(within(trustBar as HTMLElement).getByText("Bachelor • Master • PhD")).toBeInTheDocument();
    expect(within(trustBar as HTMLElement).getByText("Fully Funded")).toBeInTheDocument();
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
    const funding = within(search).getByRole("button", { name: /funding full funding/i });

    expect(destination.tagName).toBe("INPUT");
    expect(destination).toHaveAttribute("aria-controls", "desktop-destination-suggestions");
    expect(degree).toHaveAttribute("aria-controls", "degree-popover");
    expect(funding).toHaveAttribute("aria-controls", "funding-popover");
    expect(destination).toHaveAttribute("aria-expanded", "false");
  });

  it("moves active state between independent search-field surfaces", () => {
    const { container } = render(
      <BrowserRouter>
        <ScholarshipSearchHarness />
      </BrowserRouter>,
    );

    const search = screen.getByRole("search", { name: /search verified scholarships/i });
    const surfaces = container.querySelectorAll(".tns-segment-surface");

    expect(surfaces).toHaveLength(3);
    expect(search).toHaveAttribute("data-active-segment", "none");

    fireEvent.focus(within(search).getByRole("combobox", { name: /search country/i }));
    expect(search).toHaveAttribute("data-active-segment", "where");
    expect(container.querySelector(".segment-where")).toHaveClass("is-active");

    fireEvent.click(within(search).getByRole("button", { name: /degree any degree/i }));
    expect(search).toHaveAttribute("data-active-segment", "degree");
    expect(container.querySelector(".segment-where")).not.toHaveClass("is-active");
    expect(container.querySelector(".segment-degree")).toHaveClass("is-active");
  });

  it("keeps contextual popovers mounted while exposing only the active dialog", () => {
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

  it("keeps the destination dialog with its field and advances to degree", () => {
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
    expect(destination.closest(".tns-search-field")).toContainElement(destinationPopover);

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
