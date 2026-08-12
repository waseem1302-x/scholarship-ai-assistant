import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const request = vi.hoisted(() => vi.fn());
const upload = vi.hoisted(() => vi.fn());

vi.mock("../../api/client", () => ({
  ApiError: class ApiError extends Error { status = 400; },
  apiClient: { request, upload },
}));
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "student", email: "student@example.com", role: "student" }, isRestoring: false }),
}));

import { DocumentLabPage } from "./DocumentLabPage";

describe("DocumentLabPage", () => {
  beforeEach(() => { request.mockReset(); upload.mockReset(); });
  afterEach(cleanup);

  it("shows file limits and explicit per-analysis consent", async () => {
    request.mockImplementation((path: string) => {
      if (path === "/document-lab/policy") return Promise.resolve({
        enabled: true, max_upload_bytes: 10_000_000, max_pages: 50,
        max_extracted_characters: 100_000, retention_days: 30,
        notice_version: "phase7.document-data-use.v1", data_use_notice: "Private editorial guidance only.",
      });
      if (path === "/applications") return Promise.resolve({ items: [] });
      return Promise.resolve([]);
    });
    render(<BrowserRouter><DocumentLabPage /></BrowserRouter>);
    expect(await screen.findByText(/PDF or DOCX only/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/only after I request analysis/i)).not.toBeChecked();
    expect(screen.getByText(/eligibility, admission, funding, visa/i)).toBeInTheDocument();
  });
});
