import "@testing-library/jest-dom/vitest";
import "../../styles.css";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { HomepageJourneySectionContent } from "./homepageJourneyContent";
import { HomepageJourneySection } from "./HomepageJourneySection";

const section: HomepageJourneySectionContent = {
  id: "journey-test",
  title: "Build your scholarship plan",
  subtitle: "Move from credible opportunities to a focused next step.",
  actionLabel: "Open your plan",
  actionHref: "/dashboard",
  cards: [
    {
      id: "daad-epos",
      variant: "opportunity",
      eyebrow: "Check official deadline",
      title: "DAAD EPOS",
      description: "A development-focused postgraduate route.",
      badge: "Fully funded",
      href: "/catalogue?country=Germany",
      imageUrl: "/daad.jpg",
      imagePosition: "center 35%",
      favoriteId: "daad-epos",
    },
    {
      id: "chevening-playbook",
      variant: "playbook",
      eyebrow: "Chevening",
      title: "Chevening leadership evidence",
      description: "Prepare specific leadership and networking evidence.",
      badge: "Published criteria",
      href: "/assistant?prompt=chevening",
      imageUrl: "/chevening.jpg",
      sourceUrl: "https://www.chevening.org/scholarships/guidance/",
      sourceReviewedAt: "2026-09-03",
    },
    {
      id: "scholarship-cv",
      variant: "preparation",
      eyebrow: "Document task",
      title: "Scholarship CV",
      description: "Prioritize evidence relevant to the application.",
      badge: "Documents",
      href: "/document-lab",
      imageUrl: "/cv.jpg",
    },
    {
      id: "track-applications",
      variant: "next-action",
      eyebrow: "Manage progress",
      title: "Track applications",
      description: "Keep deadlines and preparation work together.",
      badge: "Execution",
      href: "/applications",
      imageUrl: "/applications.jpg",
    },
  ],
};

function renderSection(onToggleFavorite = vi.fn()) {
  render(
    <BrowserRouter>
      <HomepageJourneySection
        section={section}
        savedFavorites={new Set()}
        onToggleFavorite={onToggleFavorite}
      />
    </BrowserRouter>,
  );

  return onToggleFavorite;
}

describe("HomepageJourneySection", () => {
  afterEach(cleanup);

  it("renders the section and each card variant with only its relevant controls", () => {
    const onToggleFavorite = renderSection();

    const region = screen.getByRole("region", { name: section.title });
    expect(region).toBeInTheDocument();
    expect(screen.getByText(section.subtitle)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: section.actionLabel })).toHaveAttribute(
      "href",
      section.actionHref,
    );

    for (const card of section.cards) {
      const article = within(region).getByRole("article", { name: card.title });
      expect(within(article).getByRole("heading", { name: card.title, level: 3 })).toBeInTheDocument();
      expect(within(article).getByText(card.description)).toBeInTheDocument();
      expect(within(article).getByText(card.badge)).toBeInTheDocument();
      expect(within(article).getByRole("link", { name: `Open ${card.title}` })).toHaveAttribute(
        "href",
        card.href,
      );
    }

    const images = region.querySelectorAll("img");
    expect(images).toHaveLength(4);
    for (const image of images) {
      expect(image).toHaveAttribute("alt", "");
      expect(image).toHaveAttribute("loading", "lazy");
      expect(image).toHaveAttribute("decoding", "async");
    }
    expect(images[0]).toHaveAttribute("src", "/daad.jpg");
    expect(images[0]).toHaveStyle({ objectPosition: "center 35%" });

    const favorite = screen.getByRole("button", { name: "Save DAAD EPOS" });
    expect(favorite).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(favorite);
    expect(onToggleFavorite).toHaveBeenCalledWith("daad-epos");

    expect(screen.getByRole("link", { name: "Official criteria for Chevening" })).toHaveAttribute(
      "href",
      "https://www.chevening.org/scholarships/guidance/",
    );
    expect(screen.getByRole("link", { name: "Official criteria for Chevening" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.getByRole("link", { name: "Official criteria for Chevening" })).toHaveAttribute(
      "rel",
      "noreferrer",
    );
    expect(screen.queryAllByRole("button", { name: /save/i })).toHaveLength(1);
  });

  it("exposes the approved journey styling hooks with a semantic intro header", () => {
    renderSection();

    const region = screen.getByRole("region", { name: section.title });
    const header = region.querySelector("header.tns-home-journey-header");
    const track = within(region).getByRole("list", { name: `${section.title} cards` });

    expect(region).toHaveClass("tns-home-journey-section");
    expect(header).toBeInTheDocument();
    expect(within(region).getByRole("heading", { name: section.title, level: 2 })).toHaveClass(
      "tns-home-journey-title",
    );
    expect(screen.getByText(section.subtitle)).toHaveClass("tns-home-journey-subtitle");
    expect(track).toHaveClass("tns-home-journey-track");
    expect(region.querySelector(".tns-home-journey-card--preparation")).toBeInTheDocument();
    expect(within(region).getByRole("heading", { name: "Scholarship CV", level: 3 })).toHaveClass(
      "tns-home-journey-card__title",
    );
  });

  it("moves one visible page and updates navigation state", () => {
    renderSection();

    const region = screen.getByRole("region", { name: section.title });
    const track = within(region).getByRole("list", { name: `${section.title} cards` });
    const previous = within(region).getByRole("button", { name: "Previous" });
    const next = within(region).getByRole("button", { name: "Next" });
    const scrollBy = vi.fn(({ left }: ScrollToOptions) => {
      track.scrollLeft += left ?? 0;
      fireEvent.scroll(track);
    });

    Object.defineProperties(track, {
      clientWidth: { configurable: true, value: 600 },
      scrollWidth: { configurable: true, value: 1200 },
      scrollLeft: { configurable: true, writable: true, value: 0 },
      scrollBy: { configurable: true, value: scrollBy },
    });
    fireEvent.scroll(track);

    expect(previous).toBeDisabled();
    expect(next).toBeEnabled();

    fireEvent.click(next);

    expect(scrollBy).toHaveBeenCalledWith({ left: 600, behavior: "smooth" });
    expect(previous).toBeEnabled();
    expect(next).toBeDisabled();
  });

  it("keeps previous disabled at the track's snapped start inset", () => {
    renderSection();

    const region = screen.getByRole("region", { name: section.title });
    const track = within(region).getByRole("list", { name: `${section.title} cards` });
    const previous = within(region).getByRole("button", { name: "Previous" });

    track.style.paddingInlineStart = "4px";
    Object.defineProperties(track, {
      clientWidth: { configurable: true, value: 600 },
      scrollWidth: { configurable: true, value: 1200 },
      scrollLeft: { configurable: true, writable: true, value: 4 },
    });
    fireEvent.scroll(track);

    expect(previous).toBeDisabled();
  });

  it("offsets the legacy footer margin to preserve the journey's final spacing", () => {
    const { container } = render(
      <BrowserRouter>
        <div className="tns-home-journey">
          <HomepageJourneySection
            section={section}
            savedFavorites={new Set()}
            onToggleFavorite={vi.fn()}
          />
        </div>
        <footer className="tns-footer" />
      </BrowserRouter>,
    );

    const finalSection = container.querySelector<HTMLElement>(".tns-home-journey-section");
    const footer = container.querySelector<HTMLElement>(".tns-home-journey + .tns-footer");

    expect(getComputedStyle(finalSection!).marginBottom).toBe("64px");
    expect(getComputedStyle(footer!).marginTop).toBe("72px");
  });
});
