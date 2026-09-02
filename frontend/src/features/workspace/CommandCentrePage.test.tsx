import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getApplications: vi.fn(),
  getCommandCentre: vi.fn(),
  getNotificationPreference: vi.fn(),
}));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { id: "student-1", email: "student@example.com", role: "student" },
    isRestoring: false,
  }),
}));

vi.mock("./workspace", () => ({
  deleteApplicationData: vi.fn(),
  exportApplicationData: vi.fn(),
  getApplications: mocks.getApplications,
  getCommandCentre: mocks.getCommandCentre,
  getNotificationPreference: mocks.getNotificationPreference,
  humanize: (value: string) => value.replaceAll("_", " "),
  updateApplication: vi.fn(),
  updateApplicationTask: vi.fn(),
  updateNotificationPreference: vi.fn(),
}));

import { CommandCentrePage, DashboardSections } from "./CommandCentrePage";
import type { Application, CommandCentre } from "./types";

const centre = {
  urgent_tasks: [{ title: "Submit transcript" }],
  blocked_tasks: [{ title: "Awaiting referee" }],
  blocked_applications: [{ opportunity: { name: "Blocked scholarship" } }],
  approaching_deadlines: [{ opportunity: { name: "Deadline scholarship" } }],
  recently_changed_opportunities: [{ opportunity: { name: "Changed scholarship" } }],
  submitted_applications: [{ opportunity: { name: "Submitted scholarship" } }],
  upcoming_reminders: [{ message: "Check portal", scheduled_at: "2099-01-01T00:00:00Z" }],
} as unknown as CommandCentre;

describe("DashboardSections", () => {
  it("exposes every command-centre action group to screen readers", () => {
    render(<DashboardSections centre={centre} />);

    expect(screen.getByRole("region", { name: "Command centre overview" })).toBeVisible();
    for (const heading of [
      "Urgent actions",
      "Blocked tasks",
      "Blocked applications",
      "Approaching deadlines",
      "Recently changed opportunities",
      "Submitted applications",
      "Upcoming reminders",
    ]) expect(screen.getByRole("heading", { name: heading })).toBeVisible();
    expect(screen.getByText("Blocked scholarship")).toBeVisible();
  });
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("CommandCentrePage saved view", () => {
  it("shows only scholarships in the saved lifecycle", async () => {
    const application = (id: string, name: string, lifecycle: Application["lifecycle"]): Application => ({
      id,
      lifecycle,
      official_deadline: null,
      official_deadline_timezone: "UTC",
      official_deadline_state: "known",
      personal_deadline: null,
      personal_deadline_timezone: "UTC",
      deadline_urgency: "upcoming",
      notes: null,
      submitted_at: null,
      version: 1,
      opportunity: { id: `${id}-opportunity`, name, provider_name: "Provider" } as Application["opportunity"],
      tasks: [],
      reminders: [],
      documents: [],
    });
    mocks.getApplications.mockResolvedValue([
      application("saved-1", "Saved scholarship", "saved"),
      application("preparing-1", "Preparing scholarship", "preparing"),
    ]);
    mocks.getCommandCentre.mockResolvedValue({
      urgent_tasks: [],
      blocked_tasks: [],
      blocked_applications: [],
      approaching_deadlines: [],
      submitted_applications: [],
      upcoming_reminders: [],
      recently_changed_opportunities: [],
    });
    mocks.getNotificationPreference.mockResolvedValue({ in_app_enabled: true });

    render(
      <MemoryRouter>
        <CommandCentrePage initialLifecycle="saved" />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Saved Scholarships" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Saved scholarship" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Preparing scholarship" })).not.toBeInTheDocument();
  });
});
