import { describe, expect, it } from "vitest";
import { getHomepageJourneySections } from "./homepageJourneyContent";

describe("homepage journey content", () => {
  it("returns five purposeful sections with eight cards in both states", () => {
    for (const authenticated of [false, true]) {
      const sections = getHomepageJourneySections(authenticated);
      expect(sections).toHaveLength(5);
      expect(sections.map((section) => section.id)).toEqual([
        "funded-paths",
        "realistic-paths",
        "winning-playbooks",
        "build-evidence",
        "next-move",
      ]);
      expect(sections.every((section) => section.cards.length === 8)).toBe(true);
      expect(sections.every((section) => section.subtitle.length > 35)).toBe(true);
    }
  });

  it("does not invent personalized claims for visitors", () => {
    const serialized = JSON.stringify(getHomepageJourneySections(false));
    expect(serialized).not.toMatch(/\d+% match|winner story|selected applicant/i);
    expect(serialized).not.toContain("Check official deadline");
  });

  it("keeps every playbook attached to an official HTTPS source", () => {
    const playbooks = getHomepageJourneySections(false)[2].cards;
    expect(playbooks.every((card) => card.sourceUrl?.startsWith("https://"))).toBe(true);
    expect(playbooks.every((card) => card.sourceReviewedAt === "2026-09-03")).toBe(true);
  });

  it("defines country and degree metadata for all eight funded opportunities", () => {
    const opportunities = getHomepageJourneySections(false)[0].cards;

    expect(opportunities.map((card) => {
      if (card.variant !== "opportunity") throw new Error(`${card.title} must be an opportunity card`);
      return { title: card.title, country: card.country, degreeLevel: card.degreeLevel };
    })).toEqual([
      { title: "DAAD EPOS", country: "Germany", degreeLevel: "Postgraduate" },
      { title: "Fulbright Foreign Student Program", country: "United States", degreeLevel: "Graduate" },
      { title: "Chevening Scholarships", country: "United Kingdom", degreeLevel: "Master's" },
      { title: "Vanier Canada Graduate Scholarships", country: "Canada", degreeLevel: "Doctoral" },
      { title: "Australia Awards", country: "Partner countries", degreeLevel: "Multiple levels" },
      { title: "Erasmus Mundus Joint Masters", country: "Multiple European countries", degreeLevel: "Master's" },
      { title: "MEXT Research Scholarship", country: "Japan", degreeLevel: "Graduate research" },
      { title: "Commonwealth Master's Scholarships", country: "United Kingdom", degreeLevel: "Master's" },
    ]);

    const allOpportunityCards = getHomepageJourneySections(false)
      .flatMap((section) => section.cards)
      .filter((card) => card.variant === "opportunity");
    expect(allOpportunityCards.every((card) => card.country.length > 0 && card.degreeLevel.length > 0)).toBe(true);
  });

  it("uses the current official Cambridge source for Gates Cambridge criteria", () => {
    const playbooks = getHomepageJourneySections(false)[2].cards;
    const gatesCambridge = playbooks.find((card) => card.id === "gates-cambridge-playbook");

    expect(gatesCambridge?.sourceUrl).toBe(
      "https://www.student-funding.cam.ac.uk/fund/gates-cambridge-scholarship-2025",
    );
  });
});
