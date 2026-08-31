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
  getCatalogueCandidateObservability,
  getCatalogueRunObservability,
  importFormatForFile,
  importTemplates,
  recordSourceCheck,
  reverifySource,
} from "./admin";

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
        items: [{ id: "candidate-id", opportunity_id: "opportunity-id" }],
      })
      .mockResolvedValueOnce({ opportunity_id: "opportunity-id", tracks: [], citations: [] });

    const result = await acquireOfficialUrl(
      "https://www.mext.go.jp/example",
      "MEXT Scholarship",
      false,
      "AdminPassword2026",
      ["https://www.mext.go.jp/supporting.pdf"],
      "Example University",
    );

    expect(result.graph?.opportunity_id).toBe("opportunity-id");
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
          mode: "review_queue",
          dry_run: false,
          process_now: true,
        }),
      }),
    );
    expect(apiMocks.request).toHaveBeenNthCalledWith(
      3,
      "/admin/opportunities/opportunity-id/graph",
    );
  });

  it("loads the authorized catalogue run and candidate observability views", async () => {
    apiMocks.request
      .mockResolvedValueOnce({ run_id: "run-id" })
      .mockResolvedValueOnce({ candidate_id: "candidate-id" });

    await getCatalogueRunObservability("run-id");
    await getCatalogueCandidateObservability("candidate-id");

    expect(apiMocks.request).toHaveBeenNthCalledWith(
      1,
      "/admin/catalogue-ingestion/runs/run-id/observability",
      { signal: undefined },
    );
    expect(apiMocks.request).toHaveBeenNthCalledWith(
      2,
      "/admin/catalogue-ingestion/candidates/candidate-id/observability",
      { signal: undefined },
    );
  });
});
