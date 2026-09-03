import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createApplication: vi.fn(),
  queryState: { current: null as unknown },
  matchesState: { current: null as unknown },
}));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { id: "student-1", email: "student@example.com", role: "student" },
    isRestoring: false,
  }),
}));
vi.mock("../../hooks/useServerQuery", () => ({
  useServerQuery: (key: unknown) => {
    if (key === "detail-student-matches") {
      return {
        data: mocks.matchesState.current ?? [],
        error: null,
        isLoading: false,
        reload: vi.fn(),
      };
    }
    return mocks.queryState.current;
  },
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

const UNKNOWN_LABEL_FOR_TEST = "Not confirmed in reviewed sources";

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
  projection: {
    cycle: null,
    tracks: [],
    programmes: [],
    eligibility: [],
    deadlines: [],
    funding: [],
    documents: [],
    steps: [],
    events: [],
    resources: [],
    evidence: [],
    known_unknowns: [
      "cycle",
      "tracks",
      "programmes",
      "eligibility",
      "deadlines",
      "funding",
      "documents",
      "steps",
      "events",
      "resources",
    ],
    summary: {
      overview: {
        text: "A current overview is not confirmed in the reviewed sources.",
        evidence_ids: [],
        state: "unknown",
      },
      funding: {
        text: "Funding coverage is not confirmed in the reviewed sources.",
        evidence_ids: [],
        state: "unknown",
      },
      eligibility: {
        text: "Eligibility requirements are not confirmed in the reviewed sources.",
        evidence_ids: [],
        state: "unknown",
      },
      application_route: {
        text: "The application route is not confirmed in the reviewed sources.",
        evidence_ids: [],
        state: "unknown",
      },
    },
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

  it("does not advertise the disabled AI copilot", () => {
    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("AI Scholarship Copilot")).not.toBeInTheDocument();
    expect(screen.queryByText(/Evaluate my eligibility for Official scholarship/)).not.toBeInTheDocument();
  });

  it("does not invent documents or funding when evidence is absent", async () => {
    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      (await screen.findAllByText(UNKNOWN_LABEL_FOR_TEST)).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText(/official academic transcripts & valid passport/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/^covered$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/monthly tax-free living grant/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ielts academic 6\.5/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/free \(\$0\)/i)).not.toBeInTheDocument();
  });

  it("uses the exact unknown state instead of structural identifiers or implied facts", () => {
    mocks.queryState.current = {
      data: {
        ...opportunity,
        projection: {
          ...opportunity.projection,
          tracks: [
            {
              id: "track-unknown",
              scope: {
                cycle_id: null,
                track_id: "track-unknown",
                institution_id: null,
                programme_id: null,
                scholarship_programme_id: null,
              },
              evidence_ids: ["evidence-1"],
              code: "internal_route_code",
              parent_track_id: null,
              name: null,
              track_type: null,
              application_method: null,
              application_url: null,
              status: null,
              display_order: 0,
            },
          ],
          deadlines: [
            {
              id: "deadline-text-only",
              scope: {
                cycle_id: null,
                track_id: null,
                institution_id: null,
                programme_id: null,
                scholarship_programme_id: null,
              },
              evidence_ids: ["evidence-1"],
              deadline_type: null,
              deadline_at: null,
              deadline_text: "See the official call for the current date.",
              local_date: null,
              precision: null,
              timezone: null,
              varies_by: null,
              label: null,
              notes: null,
            },
          ],
          documents: [
            {
              id: "document-unknown",
              scope: {
                cycle_id: null,
                track_id: null,
                institution_id: null,
                programme_id: null,
                scholarship_programme_id: null,
              },
              evidence_ids: ["evidence-1"],
              document_key: "internal_document_key",
              name: null,
              required: null,
              condition: null,
              submission_stage: null,
              original_count: null,
              copy_count: null,
              translation_requirement: null,
              certification_requirement: null,
              form_year: null,
              notes: null,
              display_order: 0,
            },
          ],
          steps: [
            {
              id: "step-unknown",
              scope: {
                cycle_id: null,
                track_id: null,
                institution_id: null,
                programme_id: null,
                scholarship_programme_id: null,
              },
              evidence_ids: ["evidence-1"],
              step_code: "internal_step_code",
              title: null,
              stage_type: null,
              required: null,
              actor_type: null,
              actor_name: null,
              outcome: null,
              original_text: null,
              description: null,
              application_url: null,
              display_order: 0,
            },
          ],
        },
      },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    };

    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("Funding not confirmed")).not.toBeInTheDocument();
    expect(screen.queryByText("Not confirmed", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Deadline varies", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText(/Decision Tier:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Confidence:/i)).not.toBeInTheDocument();
    expect(screen.queryAllByText(/not confirmed in the reviewed sources/i)).toHaveLength(0);
    expect(screen.queryByText("internal_route_code")).not.toBeInTheDocument();
    expect(screen.queryByText("internal_document_key")).not.toBeInTheDocument();
    expect(screen.queryByText("internal_step_code")).not.toBeInTheDocument();
    expect(screen.queryByText("✓")).not.toBeInTheDocument();
    expect(screen.getAllByText(UNKNOWN_LABEL_FOR_TEST).length).toBeGreaterThan(3);
    expect(screen.getAllByText("See the official call for the current date.").length).toBeGreaterThan(0);
  });

  it("renders reviewed facts progressively with their citation", () => {
    const scope = {
      cycle_id: "cycle-1",
      track_id: null,
      institution_id: null,
      programme_id: null,
      scholarship_programme_id: null,
    };
    mocks.queryState.current = {
      data: {
        ...opportunity,
        projection: {
          ...opportunity.projection,
          cycle: {
            id: "cycle-1",
            scope,
            evidence_ids: ["evidence-1"],
            label: "2027 intake",
            intake_year: 2027,
            application_opening_date: null,
            application_deadline: "2027-05-30T23:59:59Z",
            status: "open",
            timezone: "UTC",
            is_rolling: false,
          },
          tracks: [
            {
              id: "track-1",
              scope: { ...scope, track_id: "track-1" },
              evidence_ids: ["evidence-1"],
              code: "embassy",
              parent_track_id: null,
              name: "Embassy route",
              track_type: "embassy",
              application_method: "Apply through the embassy",
              application_url: "https://example.com/apply",
              status: "open",
              display_order: 0,
            },
          ],
          programmes: [],
          eligibility: [
            {
              id: "eligibility-1",
              scope,
              evidence_ids: ["evidence-1"],
              rule_key: "nationality",
              rule_type: "nationality",
              operator: "in",
              value: { value: ["PK"] },
              unit: null,
              required: true,
              condition: null,
              is_exclusion: false,
              critical: true,
              original_text: "Citizens of Pakistan may apply.",
              notes: null,
              display_order: 0,
            },
          ],
          deadlines: [
            {
              id: "deadline-1",
              scope,
              evidence_ids: ["evidence-1"],
              deadline_type: "application",
              deadline_at: "2027-05-30T23:59:59Z",
              deadline_text: null,
              local_date: null,
              precision: "datetime",
              timezone: "UTC",
              varies_by: null,
              label: "Application deadline",
              notes: null,
            },
          ],
          funding: [
            {
              id: "funding-1",
              scope,
              evidence_ids: ["evidence-1"],
              component_type: "tuition",
              coverage_status: "full",
              amount: null,
              currency: null,
              frequency: null,
              unit: null,
              qualifier: null,
              original_text: "Full tuition coverage.",
              description: null,
            },
          ],
          documents: [
            {
              id: "document-1",
              scope,
              evidence_ids: ["evidence-1"],
              document_key: "passport",
              name: "Passport",
              required: true,
              condition: null,
              submission_stage: null,
              original_count: null,
              copy_count: null,
              translation_requirement: null,
              certification_requirement: null,
              form_year: null,
              notes: null,
              display_order: 0,
            },
          ],
          steps: [
            {
              id: "step-1",
              scope,
              evidence_ids: ["evidence-1"],
              step_code: "submit",
              title: "Submit online",
              stage_type: "submission",
              required: true,
              actor_type: "applicant",
              actor_name: null,
              outcome: null,
              original_text: null,
              description: "Complete the official form.",
              application_url: "https://example.com/apply",
              display_order: 0,
            },
          ],
          evidence: [
            {
              id: "evidence-1",
              entity_type: "funding",
              entity_id: "funding-1",
              field_path: "coverage_status",
              source_snapshot_id: "snapshot-1",
              source_title: "Official 2027 call",
              source_url: "https://example.com/call",
              content_hash: "hash",
              excerpt: "Full tuition coverage.",
              excerpt_start: 0,
              excerpt_end: 22,
              last_verified_at: "2026-09-01T00:00:00Z",
              verification_status: "officially_verified",
            },
          ],
          known_unknowns: ["events"],
          summary: {
            overview: { text: "Reviewed 2027 cycle.", evidence_ids: ["evidence-1"], state: "confirmed" },
            funding: { text: "Full tuition coverage.", evidence_ids: ["evidence-1"], state: "confirmed" },
            eligibility: { text: "Citizens of Pakistan may apply.", evidence_ids: ["evidence-1"], state: "confirmed" },
            application_route: { text: "Apply through the embassy.", evidence_ids: ["evidence-1"], state: "confirmed" },
          },
        },
      },
      error: null,
      isLoading: false,
      reload: vi.fn(),
    };

    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const sections = [
      screen.getByRole("region", { name: "Reviewed decision summary" }),
      screen.getByRole("region", { name: "Financial Coverage Package" }),
      screen.getByRole("region", { name: "Eligibility Criteria" }),
      screen.getByRole("region", { name: "Application Routes" }),
      screen.getByRole("region", { name: "Reviewed Deadlines" }),
      screen.getByRole("region", { name: "Required Application Documents" }),
      screen.getByRole("region", { name: "Application Steps" }),
      screen.getByRole("region", { name: "Information not yet confirmed" }),
      screen.getByRole("region", { name: "Reviewed source citations" }),
    ];
    for (let index = 0; index < sections.length - 1; index += 1) {
      expect(
        sections[index].compareDocumentPosition(sections[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
    expect(within(sections[1]).getByText("Full tuition coverage.")).toBeVisible();
    expect(within(sections[5]).getByText(/Passport · Required/)).toBeVisible();
    expect(within(sections[8]).getByRole("link", { name: /Open cited source/i })).toHaveAttribute(
      "href",
      "https://example.com/call",
    );
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

  it("does not surface a match score without field-level evidence links", () => {
    mocks.matchesState.current = [
      {
        opportunity: { id: "opportunity-1" },
        match_score: 85,
        fit_score: 85,
        fit_band: "high",
        eligibility_status: "eligible",
        eligibility_failures: [],
        failed_criteria: [],
        unknown_criteria: [],
        explanation: { satisfied: ["Degree requirement met"], missing: [], uncertain: [], next_steps: [] },
        warnings: [],
      },
    ];

    render(
      <MemoryRouter initialEntries={["/catalogue/opportunity-1"]}>
        <Routes>
          <Route path="/catalogue/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("85%")).not.toBeInTheDocument();
    expect(screen.queryByText("8500%")).not.toBeInTheDocument();
    expect(screen.queryByText("Strong Candidate Fit")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open your matches/i })).toHaveAttribute(
      "href",
      "/matches",
    );
  });
});
