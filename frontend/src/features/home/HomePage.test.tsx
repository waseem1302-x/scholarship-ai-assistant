import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ScholarshipSearch } from "../../components/ScholarshipSearch";
import { apiClient } from "../../api/client";
import type { OpportunitySearchResponse, OpportunitySummary } from "../catalogue/types";
import { initialSearch, type ActivePopover, type HomeSearchState } from "../catalogue/searchOptions";

const authState = vi.hoisted(() => ({
  user: null as { email: string; role: string } | null,
  isRestoring: false,
}));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: authState.user, isRestoring: authState.isRestoring }),
}));

import { HomePage } from "./HomePage";

function opportunity(id: string, overrides: Partial<OpportunitySummary> = {}): OpportunitySummary {
  return {
    id,
    name: `Scholarship ${id}`,
    provider_name: `Provider ${id}`,
    university_name: null,
    country: "Germany",
    degree_level: "masters",
    degree_levels: ["masters"],
    application_deadline: null,
    application_opening_date: null,
    application_timezone: "UTC",
    effective_cycle_id: null,
    funding_type: "partial",
    funding_classification: "partial",
    funding_summary: "Published funding details are available in the catalogue.",
    verification_status: "officially_verified",
    last_verified_at: "2026-09-01T00:00:00Z",
    official_source_url: `https://example.edu/${id}`,
    application_window_state: "upcoming",
    source_is_fresh: true,
    verification_freshness: "recent",
    funding_display_label: "Partial funding",
    catalogue_decision_tier: "decision_ready",
    structured_eligibility_complete: true,
    ...overrides,
  };
}

function response(items: OpportunitySummary[]): OpportunitySearchResponse {
  return {
    items,
    pagination: {
      total: items.length,
      limit: 10,
      offset: 0,
      count: items.length,
      has_next: false,
      has_previous: false,
    },
  };
}

const populatedResponse = response([
  opportunity("verified", { application_window_state: "open" }),
]);

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

const unsupportedJourneyClaimPatterns = [
  /\b\d+(?:\.\d+)?\s*%/i,
  /\b(?:winner(?:s)?|awardee(?:s)?|selected[-\s]+applicants?)\b/i,
  /\b(?:deadline|applications?\s+close[sd]?|due)(?:\s+(?:is|on))?\s*:?\s*(?:soon|today|tomorrow|\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)|(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}|\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b/i,
  /\b(?:your\s+(?:profile|application|documents?|tasks?|steps?)\s+(?:is|are)\s+(?:complete|completed|incomplete|in progress|started|submitted|saved)|you(?:'ve| have)\s+(?:saved|completed|started|submitted)\s+\d+|\d+\s*(?:of|\/)\s*\d+\s*(?:applications?|tasks?|steps?)?\s*(?:complete|completed|done))\b/i,
];

function expectJourneyToAvoidUnsupportedClaims(journey: HTMLElement) {
  const renderedText = journey.textContent ?? "";

  unsupportedJourneyClaimPatterns.forEach((pattern) => {
    expect(renderedText).not.toMatch(pattern);
  });

  expect(renderedText).not.toMatch(/check official deadline/i);
}

describe("HomePage - The Next Scholar", () => {
  beforeEach(() => {
    authState.user = null;
    authState.isRestoring = false;
    vi.spyOn(apiClient, "request").mockResolvedValue(populatedResponse);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("presents profile matching without unsupported recommendation or eligibility claims", () => {
    render(
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
    expect(within(hero).getByRole("link", { name: /explore scholarships/i })).toHaveAttribute("href", "/catalogue");
    expect(within(hero).getByText("Profile once")).toBeInTheDocument();
    expect(within(hero).getByText("Verified criteria")).toBeInTheDocument();
    expect(within(hero).getByText("Clear reasons")).toBeInTheDocument();
    expect(within(hero).getByText("Profile workflow")).toBeInTheDocument();
    expect(within(hero).getByText("How it works")).toBeInTheDocument();
    expect(within(hero).getByText("Start with verified data")).toBeInTheDocument();
    expect(within(hero).getByText("Catalogue preview")).toBeInTheDocument();
    expect(within(hero).getByRole("heading", { name: "Explore verified scholarships" })).toBeInTheDocument();
    expect(within(hero).getByText("Review published criteria")).toBeInTheDocument();
    expect(within(hero).getByRole("link", { name: /explore the catalogue/i })).toHaveAttribute("href", "/catalogue");

    [
      "Recommended opportunity",
      "Strong match",
      "Fully funded",
      "3 criteria aligned",
      "Degree requirement met",
      "Field aligned",
      "Open to your nationality",
      "Ready to match",
    ].forEach((claim) => expect(within(hero).queryByText(claim)).not.toBeInTheDocument());
  });

  it("renders the five truthful V1 sections from catalogue data and enabled workflows", async () => {
    const { container } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    await screen.findByRole("region", { name: "Verified scholarships worth exploring" });
    const journey = container.querySelector<HTMLElement>(".tns-home-journey");
    expect(journey).not.toBeNull();
    if (!journey) throw new Error("Expected the scholarship journey");

    const sections = within(journey).getAllByRole("region");
    expect(getComputedStyle(journey).backgroundColor).toBe("rgb(255, 255, 255)");
    expect(sections.map((section) => within(section).getByRole("heading", { level: 2 }).textContent)).toEqual([
      "Verified scholarships worth exploring",
      "Applications open now",
      "Explore funded study paths",
      "Check which opportunities fit you",
      "Save and build your application plan",
    ]);
    expect(within(sections[0]).getByRole("link", { name: "Open Scholarship verified" })).toHaveAttribute(
      "href",
      "/catalogue/verified",
    );
    const cardHeadingIds = Array.from(journey.querySelectorAll("article h3"), (heading) => heading.id);
    expect(new Set(cardHeadingIds).size).toBe(cardHeadingIds.length);
    expect(container.querySelectorAll('a[href^="/assistant"], a[href^="/document-lab"], a[href^="/community"]')).toHaveLength(0);
    expectJourneyToAvoidUnsupportedClaims(journey);
    expect(within(journey).queryByRole("button", { name: /^Save / })).not.toBeInTheDocument();
    expect(within(journey).queryByRole("button", { name: /^Remove .* from saved$/ })).not.toBeInTheDocument();
  });

  it("keeps the same evidence-backed section titles for signed-in students", async () => {
    authState.user = {
      email: "student@thenextscholar.com",
      role: "student",
    };

    const { container } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    await screen.findByRole("region", { name: "Verified scholarships worth exploring" });
    const journey = container.querySelector<HTMLElement>(".tns-home-journey");
    expect(journey).not.toBeNull();
    if (!journey) throw new Error("Expected the scholarship journey");

    const sections = within(journey).getAllByRole("region");
    expect(sections.map((section) => within(section).getByRole("heading", { level: 2 }).textContent)).toEqual([
      "Verified scholarships worth exploring",
      "Applications open now",
      "Explore funded study paths",
      "Check which opportunities fit you",
      "Save and build your application plan",
    ]);
    expectJourneyToAvoidUnsupportedClaims(journey);
    expect(container.querySelectorAll('a[href^="/assistant"], a[href^="/document-lab"], a[href^="/community"]')).toHaveLength(0);
  });

  it("shows neutral copy while auth restores and then renders the resolved member journey", () => {
    authState.isRestoring = true;
    const { rerender } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("Restoring your scholarship journey...")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Verified scholarships worth exploring" })).not.toBeInTheDocument();

    authState.isRestoring = false;
    authState.user = { email: "student@thenextscholar.com", role: "student" };
    rerender(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.queryByText("Restoring your scholarship journey...")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Verified scholarships worth exploring" })).toBeInTheDocument();
  });

  it("renders catalogue skeletons while the three public rows load", () => {
    vi.mocked(apiClient.request).mockImplementation(() => new Promise(() => undefined));

    const { container } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(container.querySelectorAll(".tns-home-journey-card--skeleton")).toHaveLength(9);
    expect(screen.getAllByLabelText("Loading scholarship opportunities")).toHaveLength(3);
    expect(screen.getByRole("region", { name: "Check which opportunities fit you" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Save and build your application plan" })).toBeInTheDocument();
  });

  it("omits empty catalogue rows but keeps both workflow rows", async () => {
    vi.mocked(apiClient.request).mockResolvedValue(response([]));

    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    await waitFor(() => expect(screen.queryAllByLabelText("Loading scholarship opportunities")).toHaveLength(0));
    expect(screen.queryByRole("region", { name: "Verified scholarships worth exploring" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Applications open now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Explore funded study paths" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Check which opportunities fit you" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Save and build your application plan" })).toBeInTheDocument();
  });

  it("shows one non-blocking availability message when catalogue loading fails", async () => {
    vi.mocked(apiClient.request).mockRejectedValue(new Error("offline"));

    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(await screen.findByRole("status", { name: "Catalogue availability" })).toHaveTextContent(
      "Scholarship catalogue is temporarily unavailable",
    );
    expect(screen.getAllByRole("status", { name: "Catalogue availability" })).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Check which opportunities fit you" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Save and build your application plan" })).toBeInTheDocument();
  });

  it.each([
    ["match percentage", "92% match"],
    ["winner claim", "Recent scholarship winner"],
    ["selected-applicant claim", "Selected applicant profile"],
    ["live deadline", "Deadline: 14 October 2026"],
    ["unsupported progress", "Your application is in progress"],
  ])("rejects a rendered %s", (_claimType, claim) => {
    const journey = document.createElement("div");
    journey.textContent = claim;

    expect(() => expectJourneyToAvoidUnsupportedClaims(journey)).toThrow();
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
