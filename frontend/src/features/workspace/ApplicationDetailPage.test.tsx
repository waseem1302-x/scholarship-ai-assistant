import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getApplication: vi.fn(),
  getApplicationEvents: vi.fn(),
  createApplicationTask: vi.fn(),
  updateApplicationTask: vi.fn(),
}));

const mockUser = { id: "student-1", email: "student@example.com", role: "student" };

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: mockUser,
    isRestoring: false,
  }),
}));

vi.mock("./workspace", () => ({
  getApplication: mocks.getApplication,
  getApplicationEvents: mocks.getApplicationEvents,
  createApplicationTask: mocks.createApplicationTask,
  updateApplicationTask: mocks.updateApplicationTask,
  createApplicationReminder: vi.fn(),
  updateApplicationReminder: vi.fn(),
  createApplicationDocument: vi.fn(),
  updateApplicationDocument: vi.fn(),
  updateApplication: vi.fn(),
  humanize: (val: string) => val.replaceAll("_", " "),
}));

import { ApplicationDetailPage } from "./ApplicationDetailPage";

const mockApp = {
  id: "app-1",
  opportunity: {
    name: "Chevening Scholarship",
    provider_name: "UK FCDO",
    official_source_url: "https://example.com",
  },
  lifecycle: "preparing",
  official_deadline: "2026-11-06T00:00:00Z",
  official_deadline_timezone: "UTC",
  official_deadline_state: "active",
  deadline_urgency: "upcoming",
  personal_deadline: null,
  personal_deadline_timezone: "UTC",
  version: 1,
  notes: "",
  tasks: [
    {
      id: "task-1",
      title: "Request referee letters",
      category: "recommendation",
      status: "todo",
      due_at: "2026-10-01T00:00:00Z",
      is_generated: false,
      completion_evidence: null,
    },
  ],
  reminders: [],
  documents: [],
};

describe("ApplicationDetailPage", () => {
  beforeEach(() => {
    mocks.getApplication.mockReset();
    mocks.getApplicationEvents.mockReset();
    mocks.createApplicationTask.mockReset();
    mocks.updateApplicationTask.mockReset();

    mocks.getApplication.mockResolvedValue(mockApp);
    mocks.getApplicationEvents.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it("submits taskCategory with exact snake_case enum value", async () => {
    mocks.createApplicationTask.mockResolvedValue({ id: "task-2" });

    render(
      <MemoryRouter initialEntries={["/applications/app-1"]}>
        <Routes>
          <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Chevening Scholarship");

    const input = screen.getByLabelText(/New task/i);
    const select = screen.getByLabelText(/Category/i);

    fireEvent.change(input, { target: { value: "Verify degree equivalency" } });
    fireEvent.change(select, { target: { value: "official_verification" } });

    fireEvent.click(screen.getByRole("button", { name: /Add task/i }));

    await waitFor(() => {
      expect(mocks.createApplicationTask).toHaveBeenCalledWith("app-1", {
        title: "Verify degree equivalency",
        category: "official_verification",
      });
    });
  });

  it("allows inline task editing without window.prompt", async () => {
    mocks.updateApplicationTask.mockResolvedValue({});

    render(
      <MemoryRouter initialEntries={["/applications/app-1"]}>
        <Routes>
          <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Request referee letters");

    const editBtn = screen.getByRole("button", { name: "Edit" });
    fireEvent.click(editBtn);

    const titleInput = screen.getByLabelText("Title");
    expect(titleInput).toHaveValue("Request referee letters");

    fireEvent.change(titleInput, { target: { value: "Request 2 referee letters from professors" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(mocks.updateApplicationTask).toHaveBeenCalledWith(
        "app-1",
        "task-1",
        expect.objectContaining({
          title: "Request 2 referee letters from professors",
        }),
      );
    });
  });
});
