import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const authState = vi.hoisted(() => ({
  user: null as { email: string; role: string } | null,
}));

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ user: authState.user, isRestoring: false }),
}));

import { HomePage, SearchPill, initialSearch, type ActivePopover, type HomeSearchState } from "./HomePage";

function SearchPillHarness() {
  const [search, setSearch] = useState<HomeSearchState>(initialSearch);
  const [activePopover, setActivePopover] = useState<ActivePopover>(null);

  return (
    <SearchPill
      search={search}
      activePopover={activePopover}
      onSearchChange={setSearch}
      onPopoverChange={setActivePopover}
    />
  );
}

describe("HomePage - The Next Scholar", () => {
  beforeEach(() => {
    authState.user = null;
  });

  afterEach(cleanup);

  it("renders the hero section with serif headline and crimson accent", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("Find scholarships.")).toBeInTheDocument();
    expect(screen.getByText("Build stronger applications.")).toBeInTheDocument();
    expect(
      screen.getByText(/Discover 50,000\+ verified scholarships worldwide/i),
    ).toBeInTheDocument();
  });

  it("renders the AI-powered matching banner with circular gauges", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("AI POWERED")).toBeInTheDocument();
    expect(screen.getByText(/Not sure which scholarships you qualify for\?/i)).toBeInTheDocument();
    expect(screen.getByText("87%")).toBeInTheDocument();
    expect(screen.getByText("94%")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
  });

  it("renders featured scholarships without personalized match scores before login", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("Featured scholarships")).toBeInTheDocument();
    expect(screen.getByText("DAAD Development-Related Postgraduate Courses")).toBeInTheDocument();
    expect(screen.getByText("Fulbright Foreign Student Program")).toBeInTheDocument();
    expect(screen.getByText("Chevening Scholarships 2025/26")).toBeInTheDocument();
    expect(screen.queryByText("Full Match")).not.toBeInTheDocument();
    expect(screen.queryByText("90% Match")).not.toBeInTheDocument();
    expect(screen.getAllByText("Check eligibility")).toHaveLength(5);
  });

  it("renders personalized featured match scores after login", () => {
    authState.user = {
      email: "student@thenextscholar.com",
      role: "student",
    };

    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("Full Match")).toBeInTheDocument();
    expect(screen.getAllByText("90% Match")).toHaveLength(2);
  });

  it("renders destination cards with landmark silhouettes", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    const destinationSection = screen.getByText("Browse by destination").closest("section");

    expect(destinationSection).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("Germany")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("UK")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("US")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("Canada")).toBeInTheDocument();
    expect(within(destinationSection as HTMLElement).getByText("Australia")).toBeInTheDocument();
  });

  it("renders How It Works 4-step workflow", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("How it works")).toBeInTheDocument();
    expect(screen.getByText("Discover")).toBeInTheDocument();
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByText("Track")).toBeInTheDocument();
    expect(screen.getByText("Prepare")).toBeInTheDocument();
    expect(document.querySelector(".tns-step-number-badge")).not.toBeInTheDocument();
  });

  it("renders Trust bar metrics", () => {
    render(
      <BrowserRouter>
        <HomePage />
      </BrowserRouter>,
    );

    expect(screen.getByText("500+")).toBeInTheDocument();
    expect(screen.getByText("120+")).toBeInTheDocument();
    expect(screen.getByText("Bachelor • Master • PhD")).toBeInTheDocument();
    expect(screen.getByText("Fully Funded")).toBeInTheDocument();
  });

  it("exposes the desktop scholarship search as a search landmark", () => {
    render(
      <BrowserRouter>
        <SearchPillHarness />
      </BrowserRouter>,
    );

    expect(screen.getByRole("search", { name: /search verified scholarships/i })).toBeInTheDocument();
  });

  it("renders desktop popovers outside of the active search segment", () => {
    render(
      <BrowserRouter>
        <SearchPillHarness />
      </BrowserRouter>,
    );

    const whereSegment = screen.getByText("Search destinations").closest(".tns-airbnb-segment");
    expect(whereSegment).toBeInTheDocument();

    fireEvent.click(screen.getByText("Search destinations"));

    expect(screen.getByRole("dialog", { name: /popular scholarship destinations/i })).toBeInTheDocument();
    expect(within(whereSegment as HTMLElement).queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a complete mobile search sheet with country degree and funding fields", () => {
    render(
      <BrowserRouter>
        <SearchPillHarness />
      </BrowserRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /start your search/i }));

    const mobileSheet = screen.getByRole("dialog", { name: /scholarship search/i });
    expect(within(mobileSheet).getByText("Where?")).toBeInTheDocument();
    expect(within(mobileSheet).getByText("Degree level")).toBeInTheDocument();
    expect(within(mobileSheet).getByText("Funding type")).toBeInTheDocument();
  });
});
