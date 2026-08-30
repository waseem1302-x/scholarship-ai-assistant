import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createApplication: vi.fn(),
  queryState: { current: null as unknown },
}));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { id: "student-1", email: "student@example.com", role: "student" },
    isRestoring: false,
  }),
}));
vi.mock("../../hooks/useServerQuery", () => ({
  useServerQuery: () => mocks.queryState.current,
}));
vi.mock("../workspace/workspace", () => ({
  createApplication: mocks.createApplication,
}));
vi.mock("./catalogue", () => ({
  deadlineLabel: () => "Deadline varies",
  formatDate: () => "Not stated",
  getCountryFlag: () => "🌐",
  getDeadlineUrgency: () => ({ label: "Deadline varies", tier: "varies", icon: "🗓️" }),
  getOpportunity: vi.fn(),
  isNotFound: () => false,
  readableValue: (value: unknown) => String(value ?? "unknown"),
}));

import { OpportunityDetailPage } from "./OpportunityDetailPage";

const opportunity = {
  id: "opportunity-1",
  name: "Official scholarship",
  provider_name: "Official provider",
  university_name: null,
  country: "Malaysia",
  degree_level: "masters",
  degree_levels: [],
  funding_display_label: "Funding details vary",
  funding_summary: "Review the official source for funding details.",
  data_confidence: "medium",
  verification_freshness: "recent",
  last_verified_at: null,
  tuition_coverage: null,
  monthly_stipend_amount: null,
  monthly_stipend_currency: null,
  accommodation_coverage: null,
  travel_allowance: null,
  health_insurance: null,
  application_fee_info: null,
  field_eligibility: null,
  nationality_eligibility: null,
  minimum_academic_requirement: null,
  english_language_requirement: null,
  standardized_test_requirement: null,
  application_method: null,
  application_deadline: null,
  intake_year: 2027,
  application_url: null,
  required_documents: [],
  eligibility_warnings: [],
  notes: null,
  source: {
    title: "Official source",
    relevant_excerpt: "Official source evidence for this scholarship.",
    last_verified_at: null,
    url: "https://example.com/official",
  },
};

describe("OpportunityDetailPage", () => {
  beforeEach(() => {
    mocks.queryState.current = {
      data: opportunity,
      error: null,
      isLoading: false,
      reload: vi.fn(),
    };
    mocks.createApplication.mockReset();
    mocks.createApplication.mockResolvedValue({ id: "application-1" });
  });

  afterEach(cleanup);

  it("offers a save-and-track action and links to the created application plan", async () => {
    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const saveButtons = screen.getAllByRole("button", { name: /Save & track/i });
    expect(saveButtons.length).toBeGreaterThan(0);
    fireEvent.click(saveButtons[0]);

    expect(await screen.findAllByText("Saved. Your application plan is ready.")).not.toHaveLength(0);
    const planLinks = screen.getAllByRole("link", { name: /Open application plan/i });
    expect(planLinks[0]).toHaveAttribute("href", "/applications/application-1");
  });

  it("renders the AI copilot module with tailored prompt chips", () => {
    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("AI Scholarship Copilot")).toBeInTheDocument();
    expect(screen.getByText(/Evaluate my eligibility for Official scholarship/)).toBeInTheDocument();
  });

  it("does not advertise the disabled Community feature", () => {
    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("Discuss this scholarship")).not.toBeInTheDocument();
  });
});
