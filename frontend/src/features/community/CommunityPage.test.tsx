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
  useAuth: () => ({
    user: { id: "student", email: "student@example.com", role: "student" },
    isRestoring: false,
  }),
}));

import { CommunityPage } from "./CommunityPage";

describe("CommunityPage", () => {
  beforeEach(() => request.mockReset());
  afterEach(cleanup);

  it("requires a display name and affirmative community notice before participation", async () => {
    request.mockImplementation((path: string) => {
      if (path === "/community/preferences") {
        return Promise.resolve({
          display_name: null, consented: false, suspended: false, notice_version: "v1",
        });
      }
      return Promise.resolve({ posts: [], total: 0, has_next: false });
    });
    render(<BrowserRouter><CommunityPage /></BrowserRouter>);
    expect(await screen.findByText("Choose how you appear")).toBeInTheDocument();
    expect(screen.getByText(/email, profile, applications, assistant history/i)).toBeInTheDocument();
    const consent = screen.getByRole("checkbox");
    fireEvent.click(consent);
    fireEvent.change(screen.getByLabelText("Community display name"), { target: { value: "Study pal" } });
    fireEvent.click(screen.getByRole("button", { name: "Join community" }));
    expect(request).toHaveBeenCalledWith(
      "/community/preferences",
      expect.objectContaining({ method: "PUT" }),
    );
  });

  it("renders only pseudonymous author information and allows a bookmark action", async () => {
    request.mockImplementation((path: string) => {
      if (path === "/community/preferences") {
        return Promise.resolve({ display_name: "Study pal", consented: true, suspended: false, notice_version: "v1" });
      }
      if (path === "/community/posts") {
        return Promise.resolve({
          posts: [{
            id: "post-1", title: "Checklist question", body: "How did you structure your official checklist?",
            topic: "application_process", author: { id: "author-1", display_name: "Careful applicant" },
            is_owner: false, is_bookmarked: false, reply_count: 0, created_at: "2026-08-13T00:00:00Z", opportunity: null,
          }], total: 1, has_next: false,
        });
      }
      return Promise.resolve(undefined);
    });
    render(<BrowserRouter><CommunityPage /></BrowserRouter>);
    expect(await screen.findByText(/Careful applicant/)).toBeInTheDocument();
    expect(screen.queryByText("author@example.com")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Bookmark" }));
    expect(request).toHaveBeenCalledWith(
      "/community/posts/post-1/bookmarks",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
