import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardSections } from "./CommandCentrePage";
import type { CommandCentre } from "./types";

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
