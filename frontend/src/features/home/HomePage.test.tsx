import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const queryState = vi.hoisted(() => ({ current: null as unknown }));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: null, isRestoring: false }),
}));
vi.mock("../../hooks/useServerQuery", () => ({
  useServerQuery: () => queryState.current,
}));

import { HomePage } from "./HomePage";

describe("HomePage", () => {
  beforeEach(() => {
    queryState.current = {
      data: null,
      error: null,
      isLoading: true,
      reload: vi.fn(),
    };
  });

  afterEach(cleanup);

  it("does not claim a catalogue size while the catalogue count is unknown", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.queryByText(/verified scholarships/i)).not.toBeInTheDocument();
  });

  it("uses the catalogue response as the displayed scholarship count", () => {
    queryState.current = {
      data: {
        items: [],
        pagination: {
          total: 50,
          count: 0,
          limit: 20,
          offset: 0,
          has_next: false,
          has_previous: false,
        },
      },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    };

    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText(/50 verified scholarships/i)).toBeInTheDocument();
  });

  it("presents the scholarship marketplace rows and discovery footer", () => {
    queryState.current = {
      data: {
        items: [
          {
            id: "mext",
            name: "MEXT University Recommendation",
            provider_name: "Japanese Government",
            university_name: "University of Tokyo",
            country: "Japan",
            degree_level: "bachelors",
            degree_levels: ["bachelors"],
            application_deadline: "2026-12-01",
            application_opening_date: "2026-09-01",
            application_timezone: "Asia/Tokyo",
            effective_cycle_id: "2027",
            funding_type: "full",
            funding_classification: "fully_funded",
            funding_summary: "Tuition, stipend, and travel",
            verification_status: "officially_verified",
            last_verified_at: "2026-08-31T00:00:00Z",
            official_source_url: "https://example.edu/mext",
            application_window_state: "open",
            source_is_fresh: true,
            verification_freshness: "recent",
            funding_display_label: "Fully funded",
            catalogue_decision_tier: "decision_ready",
            structured_eligibility_complete: true,
          },
          {
            id: "daad",
            name: "DAAD EPOS Scholarship",
            provider_name: "DAAD",
            university_name: null,
            country: "Germany",
            degree_level: "masters",
            degree_levels: ["masters"],
            application_deadline: "2026-10-15",
            application_opening_date: null,
            application_timezone: "Europe/Berlin",
            effective_cycle_id: "2027",
            funding_type: "partial",
            funding_classification: "partial",
            funding_summary: "Monthly stipend and allowances",
            verification_status: "officially_verified",
            last_verified_at: "2026-08-31T00:00:00Z",
            official_source_url: "https://example.edu/daad",
            application_window_state: "upcoming",
            source_is_fresh: true,
            verification_freshness: "recent",
            funding_display_label: "Partial funding",
            catalogue_decision_tier: "decision_ready",
            structured_eligibility_complete: true,
          },
        ],
        pagination: {
          total: 50,
          count: 2,
          limit: 20,
          offset: 0,
          has_next: false,
          has_previous: false,
        },
      },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    };

    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByPlaceholderText("Search countries or scholarships")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Currently open scholarships/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Fully funded bachelor/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Fully funded in Asia/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Inspiration for future applications" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Scholarships in Asia/i })).toBeInTheDocument();
  });
});
