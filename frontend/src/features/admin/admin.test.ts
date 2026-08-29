import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  adminStepUp: vi.fn(),
  request: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: apiMocks,
}));

import {
  acquireOfficialUrl,
  getAcquiredCandidateReview,
  getAcquiredCandidates,
  getDuplicateSuggestions,
  getReviewQueueItem,
  importFormatForFile,
  importTemplates,
  recordSourceCheck,
  reviewDuplicateSuggestion,
  reverifySource,
} from "./admin";
import { candidateReviewFactValue, candidateScopeLabel } from "./AdminAcquiredReviewPage";
import { candidateMatchesReviewFilter, opportunityMatchesReviewFilter, sanitizeScholarshipSearch } from "./AdminPage";
import type { AdminOpportunity, CandidateReviewFact, IngestionCandidate, ReviewQueueItem } from "./types";

describe("admin scholarship search", () => {
  it("drops browser-autofilled email addresses without changing real scholarship queries", () => {
    expect(sanitizeScholarshipSearch("reviewer@example.com")).toBe("");
    expect(sanitizeScholarshipSearch("  mr.waseem2866@gmail.com  ")).toBe("");
    expect(sanitizeScholarshipSearch("DAAD EPOS")).toBe("DAAD EPOS");
  });

  it("applies every readiness filter to backend readiness and acquisition state", () => {
    const opportunity = { id: "opportunity-id", source_is_fresh: false } as AdminOpportunity;
    const queueItem = {
      publication_readiness: {
        ready: false,
        blocking_reasons: [{ field_path: "funding.stipend", reason_code: "evidence_missing" }],
      },
      reasons: [{ code: "official_source_conflict" }],
    } as ReviewQueueItem;
    expect(opportunityMatchesReviewFilter(opportunity, "missing_funding", queueItem, new Set())).toBe(true);
    expect(opportunityMatchesReviewFilter(opportunity, "conflicts", queueItem, new Set())).toBe(true);
    expect(opportunityMatchesReviewFilter(opportunity, "duplicates", queueItem, new Set(["opportunity-id"]))).toBe(true);
    expect(opportunityMatchesReviewFilter(opportunity, "stale_sources", queueItem, new Set())).toBe(true);

    const candidate = {
      status: "validation_failed",
      failure_code: "source_fetch_failed",
      conflicts: [],
      duplicate_opportunity_ids: [],
      proposed_payload: { objective_coverage: { funding: "partial", application_timeline: "complete", eligibility: "not_stated" } },
      sources: [{ status: "failed", failure_code: "timeout", fetched_at: null, artifacts: [] }],
    } as unknown as IngestionCandidate;
    expect(candidateMatchesReviewFilter(candidate, "missing_funding")).toBe(true);
    expect(candidateMatchesReviewFilter(candidate, "missing_deadline")).toBe(false);
    expect(candidateMatchesReviewFilter(candidate, "missing_eligibility")).toBe(true);
    expect(candidateMatchesReviewFilter(candidate, "failed_acquisition")).toBe(true);
  });

  it("formats typed claim values and complete route scope", () => {
    const fact = {
      value: { string_value: null, integer_value: 2027, decimal_value: null, boolean_value: null, string_list_value: null },
      scope: { cycle_key: "intake_2027", track_key: "embassy", institution_key: null, programme_key: "masters", country_code: "JP", programme_family_key: "mext" },
    } as unknown as CandidateReviewFact;
    expect(candidateReviewFactValue(fact)).toBe("2027");
    expect(candidateScopeLabel(fact)).toContain("programme family: mext");
    expect(candidateScopeLabel(fact)).toContain("track: embassy");
  });
});

describe("import templates", () => {
  it("provides JSON and CSV templates and detects supported file names", () => {
    expect(JSON.parse(importTemplates.json)).toHaveLength(1);
    expect(importTemplates.csv).toContain("source_relevant_excerpt");
    expect(importFormatForFile("catalogue.JSON")).toBe("json");
    expect(importFormatForFile("catalogue.csv")).toBe("csv");
    expect(importFormatForFile("catalogue.xlsx")).toBeNull();
  });
});

describe("administrator source operations", () => {
  beforeEach(() => {
    apiMocks.adminStepUp.mockReset().mockResolvedValue({ step_up_token: "step-up-token" });
    apiMocks.request.mockReset().mockResolvedValue({});
  });

  it("records source checks and re-verification through password-confirmed API calls", async () => {
    await recordSourceCheck("source-id", "a".repeat(64), "Checked official call.", "AdminPassword2026");
    await reverifySource("opportunity-id", "source-id", "Confirmed unchanged.", "AdminPassword2026");

    expect(apiMocks.adminStepUp).toHaveBeenCalledTimes(2);
    expect(apiMocks.request).toHaveBeenNthCalledWith(1, "/admin/sources/source-id/checks", {
      method: "POST",
      headers: { "X-Admin-Step-Up": "step-up-token" },
      body: JSON.stringify({ content_hash: "a".repeat(64), change_summary: "Checked official call." }),
    });
    expect(apiMocks.request).toHaveBeenNthCalledWith(2, "/admin/opportunities/opportunity-id/verification", {
      method: "PATCH",
      headers: { "X-Admin-Step-Up": "step-up-token" },
      body: JSON.stringify({ source_id: "source-id", verification_status: "officially_verified", notes: "Confirmed unchanged." }),
    });
  });

  it("processes a direct official URL and loads its review graph", async () => {
    apiMocks.request
      .mockResolvedValueOnce({ id: "run-id", status: "completed" })
      .mockResolvedValueOnce({
        total: 1,
        items: [{ id: "candidate-id", opportunity_id: null }],
      });

    const result = await acquireOfficialUrl(
      "https://www.mext.go.jp/example",
      "MEXT Scholarship",
      "AdminPassword2026",
      ["https://www.mext.go.jp/supporting.pdf"],
      "Example University",
    );

    expect(result.graph).toBeNull();
    expect(apiMocks.request).toHaveBeenNthCalledWith(
      1,
      "/admin/catalogue-ingestion/runs/url",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          url: "https://www.mext.go.jp/example",
          supporting_urls: ["https://www.mext.go.jp/supporting.pdf"],
          target_name: "MEXT Scholarship",
          university: "Example University",
          mode: "candidate_only",
          dry_run: true,
          process_now: false,
        }),
      }),
    );
    expect(apiMocks.request).toHaveBeenCalledTimes(2);
  });

  it("loads one review record for the detail-first reviewer page", async () => {
    apiMocks.request.mockResolvedValueOnce({ opportunity: { id: "opportunity-id" }, reasons: [] });

    await getReviewQueueItem("opportunity-id");

    expect(apiMocks.request).toHaveBeenCalledWith(
      "/admin/review-queue/opportunity-id",
      { signal: undefined },
    );
  });

  it("loads acquired candidates and their evidence-first review projection", async () => {
    apiMocks.request
      .mockResolvedValueOnce({ total: 1, items: [{ id: "candidate-id" }] })
      .mockResolvedValueOnce({ id: "candidate-id", sources: [] })
      .mockResolvedValueOnce({ candidate_id: "candidate-id", proposed_facts: [] });

    await getAcquiredCandidates();
    const result = await getAcquiredCandidateReview("candidate-id");

    expect(apiMocks.request).toHaveBeenNthCalledWith(
      1,
      "/admin/catalogue-ingestion/candidates?limit=100&offset=0",
      { signal: undefined },
    );
    expect(apiMocks.request).toHaveBeenNthCalledWith(
      2,
      "/admin/catalogue-ingestion/candidates/candidate-id",
      { signal: undefined },
    );
    expect(apiMocks.request).toHaveBeenNthCalledWith(
      3,
      "/admin/catalogue-ingestion/candidates/candidate-id/review-projection",
      { signal: undefined },
    );
    expect(result.candidate.id).toBe("candidate-id");
  });

  it("loads duplicate comparisons and records an explicit reviewer decision", async () => {
    apiMocks.request
      .mockResolvedValueOnce({ items: [], pagination: { total: 0 } })
      .mockResolvedValueOnce({ id: "suggestion-id", status: "dismissed" });

    await getDuplicateSuggestions();
    await reviewDuplicateSuggestion("suggestion-id", false, "AdminPassword2026");

    expect(apiMocks.request).toHaveBeenNthCalledWith(
      1,
      "/admin/duplicate-suggestions?limit=100&offset=0",
      { signal: undefined },
    );
    expect(apiMocks.request).toHaveBeenNthCalledWith(
      2,
      "/admin/duplicate-suggestions/suggestion-id/decision",
      {
        method: "POST",
        headers: { "X-Admin-Step-Up": "step-up-token" },
        body: JSON.stringify({ is_duplicate: false }),
      },
    );
  });
});
