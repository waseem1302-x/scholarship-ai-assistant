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
      country: "Germany",
      degreeLevel: "Postgraduate",
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

function renderSection() {
  render(
    <BrowserRouter>
      <HomepageJourneySection section={section} />
    </BrowserRouter>,
  );
}

function pixelValue(value: string): number {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) throw new Error(`Expected a pixel value, received ${value}`);
  return parsed;
}

function containedFooterGap(footerMarginTop: string, trackMarginBottom: string): number {
  return pixelValue(footerMarginTop) + Math.min(0, pixelValue(trackMarginBottom));
}

function readCssDeclaration(mediaText: string, selector: string, property: string): string {
  for (const styleSheet of Array.from(document.styleSheets)) {
    for (const rule of Array.from(styleSheet.cssRules)) {
      const mediaRule = rule as CSSMediaRule;
      if (mediaRule.media?.mediaText !== mediaText) continue;

      for (const nestedRule of Array.from(mediaRule.cssRules)) {
        const styleRule = nestedRule as CSSStyleRule;
        if (styleRule.selectorText === selector) {
          const value = styleRule.style.getPropertyValue(property);
          if (value) return value;
        }
      }
    }
  }

  throw new Error(`Missing ${property} for ${selector} in ${mediaText}`);
}

describe("HomepageJourneySection", () => {
  afterEach(cleanup);

  it("renders the section and each card variant with only its relevant controls", () => {
    renderSection();

    const region = screen.getByRole("region", { name: section.title });
    expect(region).toBeInTheDocument();
    expect(screen.getByText(section.subtitle)).toBeInTheDocument();
    const sectionAction = screen.getByRole("link", { name: section.actionLabel });
    expect(sectionAction).toHaveAttribute(
      "href",
      section.actionHref,
    );
    expect(sectionAction.querySelector("svg")).toBeInTheDocument();

    for (const card of section.cards) {
      const article = within(region).getByRole("article", { name: card.title });
      expect(within(article).getByRole("heading", { name: card.title, level: 3 })).toBeInTheDocument();
      expect(within(article).queryByText(card.description)).not.toBeInTheDocument();
      expect(within(article).getByText(card.badge)).toBeInTheDocument();
      expect(within(article).getByRole("link", { name: `Open ${card.title}` })).toHaveAttribute(
        "href",
        card.href,
      );
      expect(article.querySelectorAll(".tns-home-journey-card__support")).toHaveLength(1);
    }

    expect(within(region).queryByText("Check official deadline")).not.toBeInTheDocument();
    expect(within(region).queryByText("Reviewed 2026-09-03")).not.toBeInTheDocument();

    const images = region.querySelectorAll("img");
    expect(images).toHaveLength(4);
    for (const image of images) {
      expect(image).toHaveAttribute("alt", "");
      expect(image).toHaveAttribute("loading", "lazy");
      expect(image).toHaveAttribute("decoding", "async");
    }
    expect(images[0]).toHaveAttribute("src", "/daad.jpg");
    expect(images[0]).toHaveStyle({ objectPosition: "center 35%" });

    const opportunity = within(region).getByRole("article", { name: "DAAD EPOS" });
    const metadata = within(opportunity).getByLabelText("DAAD EPOS opportunity details");
    expect(within(metadata).getByText("Germany")).toBeVisible();
    expect(within(metadata).getByText("Postgraduate")).toBeVisible();

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
    expect(screen.queryAllByRole("button", { name: /save/i })).toHaveLength(0);
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
    const navigation = within(region).getByRole("group", {
      name: `${section.title} carousel navigation`,
    });
    const previous = within(navigation).getByRole("button", {
      name: `Previous cards in ${section.title}`,
    });
    const next = within(navigation).getByRole("button", {
      name: `Next cards in ${section.title}`,
    });
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
    const previous = within(region).getByRole("button", {
      name: `Previous cards in ${section.title}`,
    });

    track.style.paddingInlineStart = "4px";
    Object.defineProperties(track, {
      clientWidth: { configurable: true, value: 600 },
      scrollWidth: { configurable: true, value: 1200 },
      scrollLeft: { configurable: true, writable: true, value: 4 },
    });
    fireEvent.scroll(track);

    expect(previous).toBeDisabled();
  });

  it("allows two-line badges without reserving space for unavailable favorite controls", () => {
    renderSection();

    const opportunity = screen.getByRole("article", { name: "DAAD EPOS" });
    const playbook = screen.getByRole("article", { name: "Chevening leadership evidence" });
    const opportunityMedia = opportunity.querySelector(".tns-home-journey-card__media");
    const playbookMedia = playbook.querySelector(".tns-home-journey-card__media");
    const opportunityBadge = within(opportunity).getByText("Fully funded");
    const playbookBadge = within(playbook).getByText("Published criteria");

    expect(opportunityMedia).not.toHaveClass("tns-home-journey-card__media--has-favorite");
    expect(playbookMedia).not.toHaveClass("tns-home-journey-card__media--has-favorite");
    expect(getComputedStyle(opportunityBadge).whiteSpace).toBe("normal");
    expect(getComputedStyle(opportunityBadge).maxWidth).toBe("calc(100% - 24px)");
    expect(getComputedStyle(playbookBadge).maxWidth).toBe("calc(100% - 24px)");
    expect(getComputedStyle(playbookBadge).overflow).toBe("visible");
    expect(getComputedStyle(playbookBadge).getPropertyValue("-webkit-line-clamp")).toBe("");
  });

  it("keeps the mobile carousel inset and its compact card contract", () => {
    renderSection();

    expect(
      readCssDeclaration("(max-width: 743px)", ".tns-home-journey-header", "padding-inline"),
    ).toBe("20px");
    expect(
      readCssDeclaration("(max-width: 743px)", ".tns-home-journey-track", "padding-inline"),
    ).toBe("20px");
    expect(
      readCssDeclaration("(max-width: 743px)", ".tns-home-journey-track", "scroll-padding-inline"),
    ).toBe("20px");
    expect(
      readCssDeclaration("(max-width: 743px)", ".tns-home-journey-track", "grid-auto-columns"),
    ).toBe("clamp(156px, 42vw, 164px)");
    expect(
      readCssDeclaration("(max-width: 743px)", ".tns-home-journey-action-label", "display"),
    ).toBe("none");
  });

  it("preserves 64px desktop/tablet and 48px mobile footer gaps inside the white wrapper", () => {
    const { container } = render(
      <BrowserRouter>
        <div className="tns-home-journey">
          <HomepageJourneySection section={section} />
        </div>
        <footer className="tns-footer" />
      </BrowserRouter>,
    );

    const finalSection = container.querySelector<HTMLElement>(".tns-home-journey-section");
    const footer = container.querySelector<HTMLElement>(".tns-home-journey + .tns-footer");
    const track = container.querySelector<HTMLElement>(".tns-home-journey-track");

    expect(getComputedStyle(finalSection!).marginBottom).toBe("0px");
    expect(
      containedFooterGap(
        getComputedStyle(footer!).marginTop,
        getComputedStyle(track!).marginBottom,
      ),
    ).toBe(64);
    expect(
      readCssDeclaration("(max-width: 743px)", ".tns-home-journey-section:last-child", "margin-bottom"),
    ).toBe("0px");
    expect(
      containedFooterGap(
        readCssDeclaration("(max-width: 743px)", ".tns-home-journey + .tns-footer", "margin-top"),
        getComputedStyle(track!).marginBottom,
      ),
    ).toBe(48);
  });
});
