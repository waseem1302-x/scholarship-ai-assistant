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
    );

    expect(result.graph?.opportunity_id).toBe("opportunity-id");
    expect(apiMocks.request).toHaveBeenNthCalledWith(
      1,
      "/admin/catalogue-ingestion/runs/url",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          url: "https://www.mext.go.jp/example",
          target_name: "MEXT Scholarship",
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
});
