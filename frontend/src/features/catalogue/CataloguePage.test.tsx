import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { OpportunitySearchResponse, OpportunitySummary } from "./types";

const queryState = vi.hoisted(() => ({
  resultsByQuery: {} as Record<string, OpportunitySearchResponse>,
}));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: null, isRestoring: false }),
}));

vi.mock("../../hooks/useServerQuery", () => ({
  useServerQuery: (key: string, _loader: unknown, enabled = true) => {
    const q = new URLSearchParams(key).get("q") ?? "";
    return {
      data: enabled ? queryState.resultsByQuery[q] : undefined,
      error: null,
      isLoading: false,
      reload: vi.fn(),
    };
  },
}));

import { CataloguePage } from "./CataloguePage";

function opportunity(
  id: string,
  name: string,
  providerName: string,
  fundingSummary: string,
): OpportunitySummary {
  return {
    id,
    name,
    provider_name: providerName,
    university_name: null,
    country: "Multiple countries",
    degree_level: "masters",
    application_deadline: null,
    application_opening_date: null,
    application_timezone: "UTC",
    effective_cycle_id: null,
    funding_type: "full",
    funding_summary: fundingSummary,
    verification_status: "officially_verified",
    last_verified_at: "2026-09-01T00:00:00Z",
    official_source_url: "https://example.edu/scholarship",
    application_window_state: "deadline_unknown",
    source_is_fresh: true,
    verification_freshness: "recent",
    funding_display_label: "Fully funded",
    catalogue_decision_tier: "decision_ready",
    structured_eligibility_complete: true,
  };
}

const catalogueItems = [
  opportunity(
    "development",
    "Development Leadership Scholarship",
    "International Development Institute",
    "Funding for development-focused professionals.",
  ),
  opportunity(
    "government",
    "Australia Awards",
    "Australian Government",
    "Publicly funded graduate study.",
  ),
  opportunity(
    "joint-masters",
    "Erasmus Mundus Joint Masters",
    "European Commission",
    "Joint study across participating institutions.",
  ),
  opportunity("decoy", "Independent Research Award", "Example Foundation", "Research support."),
];

function response(items: OpportunitySummary[], total = items.length): OpportunitySearchResponse {
  return {
    items,
    pagination: {
      total,
      limit: 10,
      offset: 0,
      count: items.length,
      has_next: total > items.length,
      has_previous: false,
    },
  };
}

function renderCatalogue(q: string) {
  queryState.resultsByQuery = {
    development: response([catalogueItems[0]]),
    government: response([catalogueItems[1]]),
    "joint masters": response([catalogueItems[2]]),
  };
  window.history.pushState({}, "", `/catalogue?q=${encodeURIComponent(q)}`);
  return render(
    <BrowserRouter>
      <CataloguePage />
    </BrowserRouter>,
  );
}

afterEach(() => {
  cleanup();
  queryState.resultsByQuery = {};
  window.history.pushState({}, "", "/");
});

describe("CataloguePage homepage keyword routes", () => {
  it.each([
    ["development", "Development Leadership Scholarship"],
    ["government", "Australia Awards"],
    ["joint masters", "Erasmus Mundus Joint Masters"],
  ])("hydrates q=%s into the search and filters the displayed results", (q, expectedName) => {
    renderCatalogue(q);

    expect(screen.getByRole("textbox", { name: "Search query" })).toHaveValue(q);
    expect(screen.getByRole("heading", { name: expectedName })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Independent Research Award" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "1 scholarships found" })).toBeInTheDocument();
  });

  it("keeps the URL and visible results in sync when the keyword changes", async () => {
    renderCatalogue("development");

    const search = screen.getByRole("textbox", { name: "Search query" });
    fireEvent.change(search, { target: { value: "government" } });
    fireEvent.submit(search.closest("form")!);

    await waitFor(() => expect(new URLSearchParams(window.location.search).get("q")).toBe("government"));
    expect(screen.getByRole("heading", { name: "Australia Awards" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Development Leadership Scholarship" })).not.toBeInTheDocument();
  });

  it("uses the server-filtered page and total without filtering only the current page again", () => {
    const backendMatch = opportunity(
      "backend-match",
      "Public Service Scholarship",
      "Leadership Council",
      "Fully funded graduate study.",
    );
    queryState.resultsByQuery = { government: response([backendMatch], 12) };
    window.history.pushState({}, "", "/catalogue?q=government");

    render(
      <BrowserRouter>
        <CataloguePage />
      </BrowserRouter>,
    );

    expect(screen.getByRole("heading", { name: "Public Service Scholarship" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "12 scholarships found" })).toBeInTheDocument();
  });
});
