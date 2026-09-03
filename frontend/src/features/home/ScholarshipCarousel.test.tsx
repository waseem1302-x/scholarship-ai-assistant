import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScholarshipCarousel, type ScholarshipCarouselItem } from "./ScholarshipCarousel";

const items: ScholarshipCarouselItem[] = Array.from({ length: 8 }, (_, index) => ({
  id: `scholarship-${index + 1}`,
  name: `Scholarship ${index + 1}`,
  country: "Germany",
  flag: "🇩🇪",
  degreeLevel: "Master's",
  deadline: "31 Oct 2026",
  badge: "Verified",
  href: "/catalogue?country=Germany",
  imageUrl: "/campus.jpg",
}));

describe("ScholarshipCarousel", () => {
  afterEach(cleanup);

  it("delegates favorite changes with the scholarship id", () => {
    const onToggleFavorite = vi.fn();

    render(
      <BrowserRouter>
        <ScholarshipCarousel
          id="recommended"
          title="Recommended for You"
          items={items}
          savedFavorites={new Set()}
          onToggleFavorite={onToggleFavorite}
        />
      </BrowserRouter>,
    );

    const favoriteButton = screen.getByRole("button", { name: "Save Scholarship 1" });

    expect(favoriteButton).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(favoriteButton);

    expect(onToggleFavorite).toHaveBeenCalledWith("scholarship-1");
  });

  it("moves one visible page and updates navigation state", () => {
    render(
      <BrowserRouter>
        <ScholarshipCarousel
          id="recommended"
          title="Recommended for You"
          items={items}
          savedFavorites={new Set()}
          onToggleFavorite={() => undefined}
        />
      </BrowserRouter>,
    );

    const section = screen.getByRole("region", { name: "Recommended for You" });
    const track = within(section).getByRole("list", { name: "Recommended for You scholarships" });
    const previous = within(section).getByRole("button", { name: "Previous" });
    const next = within(section).getByRole("button", { name: "Next" });

    Object.defineProperties(track, {
      clientWidth: { configurable: true, value: 600 },
      scrollWidth: { configurable: true, value: 1200 },
      scrollLeft: { configurable: true, writable: true, value: 0 },
      scrollBy: {
        configurable: true,
        value: ({ left }: ScrollToOptions) => {
          track.scrollLeft += left ?? 0;
          fireEvent.scroll(track);
        },
      },
    });
    fireEvent.scroll(track);

    expect(previous).toBeDisabled();
    expect(next).toBeEnabled();

    fireEvent.click(next);

    expect(track.scrollLeft).toBe(600);
    expect(previous).toBeEnabled();
    expect(next).toBeDisabled();
  });
});
