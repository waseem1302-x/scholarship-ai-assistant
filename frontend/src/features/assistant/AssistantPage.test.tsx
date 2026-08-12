import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const request = vi.hoisted(() => vi.fn());

vi.mock("../../api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
  apiClient: { request },
}));
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "student", email: "student@example.com" }, isRestoring: false }),
}));

import { AssistantPage } from "./AssistantPage";

describe("AssistantPage", () => {
  beforeEach(() => {
    request.mockReset();
  });
  afterEach(cleanup);

  it("requires visible consent before a question can be submitted", async () => {
    request.mockImplementation((path: string) => {
      if (path === "/assistant/preferences") return Promise.resolve({
        consented: false,
        history_enabled: true,
        history_retention_days: 30,
        feedback_retention_days: 365,
      });
      return Promise.resolve([]);
    });
    render(<BrowserRouter><AssistantPage /></BrowserRouter>);
    expect(await screen.findByText("Data-use notice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask assistant" })).toBeDisabled();
  });

  it("keeps private application data opt-in separate from profile matching", async () => {
    request.mockImplementation((path: string) => {
      if (path === "/assistant/preferences") return Promise.resolve({
        consented: true,
        history_enabled: true,
        history_retention_days: 30,
        feedback_retention_days: 365,
      });
      return Promise.resolve([]);
    });
    render(<BrowserRouter><AssistantPage /></BrowserRouter>);
    const optIn = await screen.findByLabelText(/Use my private application workspace/i);
    expect(optIn).not.toBeChecked();
    fireEvent.click(optIn);
    expect(optIn).toBeChecked();
  });
});
