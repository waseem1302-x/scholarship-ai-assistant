import { describe, expect, it } from "vitest";

import {
  catalogueSearch,
  deadlineLabel,
  filtersFromSearch,
  formatCardDeadline,
  getDestinationImage,
  getInclusionsSummary,
  getOpportunityBadges,
} from "./catalogue";
import { defaultCatalogueFilters, type OpportunitySummary } from "./types";
import { filterDestinationOptions, resolveDestinationOption } from "./searchOptions";

describe("catalogue query contract", () => {
  it("filters canonical destinations and resolves common aliases", () => {
    expect(filterDestinationOptions("jap").map((option) => option.country)).toEqual(["Japan"]);
    expect(resolveDestinationOption(" uk ")?.country).toBe("United Kingdom");
    expect(resolveDestinationOption("Atlantis")).toBeNull();
  });

  it("keeps open-now enabled and includes only selected structured filters", () => {
    const params = catalogueSearch(
      {
        availability: "open",
        country: "Malaysia",
        degree_level: "masters",
        funding_type: "full",
        field: "Computer Science",
        nationality: "",
        limit: "20",
      },
      20,
    );

    expect(params.toString()).toBe(
      "availability=open&limit=20&offset=20&open_now=true&country=Malaysia&degree_level=masters&funding_type=full&field=Computer+Science",
    );
  });

  it("uses the upcoming state filter or no window filter for all verified records", () => {
    const upcoming = catalogueSearch({ ...defaultCatalogueFilters, availability: "upcoming" });
    const all = catalogueSearch({ ...defaultCatalogueFilters, availability: "all" });

    expect(upcoming.toString()).toBe(
      "availability=upcoming&limit=10&offset=0&application_window_state=upcoming",
    );
    expect(all.toString()).toBe("availability=all&limit=10&offset=0");
  });

  it("normalizes invalid URL values to all verified by default", () => {
    expect(filtersFromSearch(new URLSearchParams("country=UK&limit=100&degree_level=unsupported"))).toEqual({
      availability: "all",
      country: "UK",
      degree_level: "",
      funding_type: "",
      field: "",
      nationality: "",
      limit: "10",
    });
  });

  it("presents unknown and close deadlines without declaring an opportunity open", () => {
    expect(deadlineLabel(null)).toBe("Deadline varies");
    expect(deadlineLabel(new Date(Date.now() + 86_400_000).toISOString())).toBe("1 days left");
  });

  it("resolves destination images based on country and program name", () => {
    const ukImg = getDestinationImage("United Kingdom", "Chevening Scholarships");
    const deImg = getDestinationImage("Germany", "DAAD EPOS");
    const jpImg = getDestinationImage("Japan", "MEXT Research");
    const fallbackImg = getDestinationImage("Somewhere", "Generic Scholarship");

    expect(ukImg).toContain("unsplash.com");
    expect(deImg).toContain("unsplash.com");
    expect(jpImg).toContain("unsplash.com");
    expect(fallbackImg).toContain("unsplash.com");
  });

  it("computes opportunity badges for fully funded top awards", () => {
    const opp: OpportunitySummary = {
      id: "test-1",
      name: "Chevening Scholarships",
      provider_name: "UK Government",
      university_name: null,
      country: "United Kingdom",
      degree_level: "masters",
      application_deadline: "2026-11-05T00:00:00Z",
      application_opening_date: "2026-08-01T00:00:00Z",
      application_timezone: "UTC",
      effective_cycle_id: "cycle-1",
      funding_type: "full",
      funding_classification: "fully_funded",
      funding_summary: "Tuition, living costs, travel",
      verification_status: "officially_verified",
      last_verified_at: "2026-08-15T00:00:00Z",
      official_source_url: "https://chevening.org",
      application_window_state: "open",
      source_is_fresh: true,
      verification_freshness: "recent",
      funding_display_label: "100% Full Ride",
      catalogue_decision_tier: "decision_ready",
      structured_eligibility_complete: true,
    };

    const badges = getOpportunityBadges(opp);
    expect(badges.fundingBadge.label).toBe("Fully Funded");
    expect(badges.fundingBadge.tier).toBe("full");
    expect(badges.highlightBadge?.label).toBe("Top opportunity");

    const inclusions = getInclusionsSummary(opp);
    expect(inclusions).toBe("Tuition, living costs, travel");

    const formattedDeadline = formatCardDeadline(opp.application_deadline);
    expect(formattedDeadline).toContain("Nov 5, 2026");
  });
});
