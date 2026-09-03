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

  if (journey.querySelector(".tns-home-journey-card")) {
    const deadlineCues = Array.from(
      journey.querySelectorAll<HTMLElement>(".tns-home-journey-card__eyebrow"),
    ).filter((cue) => /deadline/i.test(cue.textContent ?? ""));

    expect(deadlineCues).toHaveLength(8);
    deadlineCues.forEach((cue) => {
      expect(cue).toHaveTextContent(/^Check official deadline$/);
    });
  }
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

  it("renders the five-stage scholarship journey for visitors", () => {
    const { container } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    const expectedSections = [
      {
        title: "Funded paths to your next chapter",
        subtitle: "Start with credible opportunities for international students—not another endless directory.",
        actionLabel: "Explore scholarships",
        actionHref: "/catalogue",
      },
      {
        title: "Scholarships with a realistic path",
        subtitle: "Compare funding, degree level, deadline, and eligibility before investing weeks in an application.",
        actionLabel: "Check your eligibility",
        actionHref: "/profile",
      },
      {
        title: "Scholarship winning playbooks",
        subtitle: "Understand what major scholarships evaluate—and how to prepare evidence before you apply.",
        actionLabel: "Explore playbooks",
        actionHref: "/assistant",
      },
      {
        title: "Build what selectors score",
        subtitle: "Strengthen the essays, evidence, documents, and interview answers behind a serious application.",
        actionLabel: "Start preparing",
        actionHref: "/assistant",
      },
      {
        title: "Start from where you are",
        subtitle: "Choose your current stage and go directly to the tool that moves your application forward.",
        actionLabel: "Build your plan",
        actionHref: "/profile",
      },
    ];
    const journey = container.querySelector<HTMLElement>(".tns-home-journey");

    expect(journey).not.toBeNull();
    if (!journey) throw new Error("Expected the scholarship journey");

    const sections = within(journey).getAllByRole("region");

    expect(sections).toHaveLength(expectedSections.length);

    sections.forEach((section, index) => {
      const expected = expectedSections[index];
      const action = section.querySelector<HTMLAnchorElement>(".tns-home-journey-action");

      expect(within(section).getByRole("heading", { name: expected.title })).toBeInTheDocument();
      expect(within(section).getByText(expected.subtitle)).toBeInTheDocument();
      expect(action?.textContent).toBe(expected.actionLabel);
      expect(action).toHaveAttribute("href", expected.actionHref);
      expect(within(section).getAllByRole("article")).toHaveLength(8);
    });

    const playbooks = within(journey).getByRole("region", {
      name: "Scholarship winning playbooks",
    });
    const officialSource = within(playbooks).getAllByRole("link", { name: /official criteria/i })[0];

    expect(officialSource).toHaveAttribute("href", expect.stringMatching(/^https:\/\//));
    expectJourneyToAvoidUnsupportedClaims(journey);
    expect(screen.queryByText("AI POWERED")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "How it works" })).not.toBeInTheDocument();
    expect(screen.queryByText("Browse by destination")).not.toBeInTheDocument();

    const favorite = within(journey).getByRole("button", { name: "Remove DAAD EPOS from saved" });
    fireEvent.click(favorite);
    expect(within(journey).getByRole("button", { name: "Save DAAD EPOS" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("renders the five-stage scholarship journey for signed-in students", () => {
    authState.user = {
      email: "student@thenextscholar.com",
      role: "student",
    };

    const { container } = render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    const expectedSections = [
      {
        title: "Continue exploring funded opportunities",
        subtitle: "Open an opportunity, inspect its criteria, and decide whether it belongs in your plan.",
        actionLabel: "View your matches",
        actionHref: "/matches",
      },
      {
        title: "Turn your profile into better decisions",
        subtitle: "Use explainable matching to separate confirmed alignment from missing or uncertain information.",
        actionLabel: "Inspect your matches",
        actionHref: "/matches",
      },
      {
        title: "Prepare for the scholarships you are targeting",
        subtitle: "Turn selection criteria into focused questions, evidence, and application tasks.",
        actionLabel: "Open AI coach",
        actionHref: "/assistant",
      },
      {
        title: "Strengthen your application evidence",
        subtitle: "Continue with the highest-impact part of your application instead of guessing what to do next.",
        actionLabel: "Open document lab",
        actionHref: "/document-lab",
      },
      {
        title: "Your next best move",
        subtitle: "Resume your profile, matches, documents, or applications from one clear starting point.",
        actionLabel: "Open workspace",
        actionHref: "/dashboard",
      },
    ];
    const journey = container.querySelector<HTMLElement>(".tns-home-journey");

    expect(journey).not.toBeNull();
    if (!journey) throw new Error("Expected the scholarship journey");

    const sections = within(journey).getAllByRole("region");

    expect(sections).toHaveLength(expectedSections.length);

    sections.forEach((section, index) => {
      const expected = expectedSections[index];
      const action = section.querySelector<HTMLAnchorElement>(".tns-home-journey-action");

      expect(within(section).getByRole("heading", { name: expected.title })).toBeInTheDocument();
      expect(within(section).getByText(expected.subtitle)).toBeInTheDocument();
      expect(action?.textContent).toBe(expected.actionLabel);
      expect(action).toHaveAttribute("href", expected.actionHref);
      expect(within(section).getAllByRole("article")).toHaveLength(8);
    });

    expectJourneyToAvoidUnsupportedClaims(journey);
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
