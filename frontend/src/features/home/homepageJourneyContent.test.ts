import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import type { OpportunitySearchResponse, OpportunitySummary } from "../catalogue/types";
import { loadHomepageOpportunityRows } from "./homepageJourney";
import { getHomepageJourneySections } from "./homepageJourneyContent";

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

describe("homepage journey data", () => {
  afterEach(() => vi.restoreAllMocks());

  it("builds scholarship rows from the three public catalogue responses", async () => {
    const verified = opportunity("verified");
    const open = opportunity("open", { application_window_state: "open" });
    const funded = opportunity("funded", {
      country: "Japan",
      funding_type: "full",
      funding_classification: "fully_funded",
      funding_display_label: "Full funding",
    });
    const request = vi
      .spyOn(apiClient, "request")
      .mockResolvedValueOnce(response([verified]))
      .mockResolvedValueOnce(response([open]))
      .mockResolvedValueOnce(response([funded]));

    const rows = await loadHomepageOpportunityRows();

    expect(rows.verified[0]).toMatchObject({
      opportunityId: "verified",
      href: "/catalogue/verified",
      title: "Scholarship verified",
    });
    expect(rows.open.every((item) => item.applicationWindowState === "open")).toBe(true);
    expect(rows.funded[0]).toMatchObject({
      opportunityId: "funded",
      href: "/catalogue/funded",
      country: "Japan",
    });
    expect(rows.funded[0].imageUrl).toContain("/assets/home-journey/path-japan.webp");
    expect(request.mock.calls.map(([path]) => path)).toEqual([
      "/opportunities?availability=all&limit=10&offset=0",
      "/opportunities?availability=open&limit=10&offset=0&open_now=true",
      "/opportunities?availability=all&limit=10&offset=0&funding_type=full",
    ]);
  });

  it("builds the five V1 sections from catalogue rows and enabled workflows", async () => {
    vi.spyOn(apiClient, "request")
      .mockResolvedValueOnce(response([opportunity("verified")]))
      .mockResolvedValueOnce(response([opportunity("open", { application_window_state: "open" })]))
      .mockResolvedValueOnce(response([opportunity("funded", { funding_type: "full" })]));

    const sections = getHomepageJourneySections(await loadHomepageOpportunityRows());

    expect(sections.map((section) => section.title)).toEqual([
      "Verified scholarships worth exploring",
      "Applications open now",
      "Explore funded study paths",
      "Check which opportunities fit you",
      "Save and build your application plan",
    ]);
    expect(sections.slice(0, 3).every((section) => section.cards[0].href.startsWith("/catalogue/"))).toBe(true);
    expect(sections.slice(0, 3).flatMap((section) => section.cards).every((card) => !("favoriteId" in card))).toBe(true);

    const workflowHrefs = sections.slice(3).flatMap((section) => section.cards.map((card) => card.href));
    expect(workflowHrefs).toEqual([
      "/profile",
      "/matches",
      "/catalogue",
      "/applications",
      "/dashboard",
    ]);
    expect(JSON.stringify(sections)).not.toMatch(/\/(assistant|document-lab|community)/);
  });

  it("omits an empty catalogue row without replacing it with invented scholarships", () => {
    const sections = getHomepageJourneySections({ verified: [], open: [], funded: [] });

    expect(sections.map((section) => section.title)).toEqual([
      "Check which opportunities fit you",
      "Save and build your application plan",
    ]);
  });
});
