import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import type {
  HomepageJourneyCard,
  HomepageJourneySectionContent,
} from "./homepageJourneyContent";
import "./homepage-journey.css";

interface HomepageJourneySectionProps {
  section: HomepageJourneySectionContent;
  isLoading?: boolean;
}

interface HomepageJourneyCardViewProps {
  card: HomepageJourneyCard;
}

function HomepageJourneyCardView({ card }: HomepageJourneyCardViewProps) {
  const titleId = `${card.id}-title`;

  return (
    <article
      className={`tns-home-journey-card tns-home-journey-card--${card.variant}`}
      aria-labelledby={titleId}
    >
      <div className="tns-home-journey-card__media">
        <Link
          to={card.href}
          className="tns-home-journey-card__image-link"
          aria-label={`Open ${card.title}`}
        >
          <img
            src={card.imageUrl}
            alt=""
            loading="lazy"
            decoding="async"
            style={{ objectPosition: card.imagePosition ?? "center" }}
          />
        </Link>
        <span className="tns-home-journey-card__badge">{card.badge}</span>

      </div>

      <div className="tns-home-journey-card__copy">
        <h3 id={titleId} className="tns-home-journey-card__title">
          <Link to={card.href}>{card.title}</Link>
        </h3>
        {card.variant === "opportunity" ? (
          <dl
            className="tns-home-journey-card__metadata tns-home-journey-card__support"
            aria-label={`${card.title} opportunity details`}
          >
            <div>
              <dt className="sr-only">Country</dt>
              <dd>{card.country}</dd>
            </div>
            <div>
              <dt className="sr-only">Degree level</dt>
              <dd>{card.degreeLevel}</dd>
            </div>
          </dl>
        ) : card.sourceUrl ? (
          <div className="tns-home-journey-card__source tns-home-journey-card__support">
            <a
              href={card.sourceUrl}
              target="_blank"
              rel="noreferrer"
              aria-label={`Official criteria for ${card.eyebrow}`}
            >
              Official criteria
            </a>
          </div>
        ) : (
          <p className="tns-home-journey-card__support">{card.eyebrow}</p>
        )}
      </div>
    </article>
  );
}

export function HomepageJourneySection({
  section,
  isLoading = false,
}: HomepageJourneySectionProps) {
  const titleId = `${section.id}-title`;
  const trackId = `${section.id}-track`;
  const trackRef = useRef<HTMLUListElement>(null);
  const [canScrollPrevious, setCanScrollPrevious] = useState(false);
  const [canScrollNext, setCanScrollNext] = useState(false);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;

    const updateNavigation = () => {
      const maximumScroll = Math.max(0, track.scrollWidth - track.clientWidth);
      const startingOffset = Number.parseFloat(getComputedStyle(track).paddingInlineStart) || 0;
      setCanScrollPrevious(track.scrollLeft > startingOffset + 1);
      setCanScrollNext(track.scrollLeft < maximumScroll - 1);
    };

    updateNavigation();
    track.addEventListener("scroll", updateNavigation, { passive: true });
    window.addEventListener("resize", updateNavigation);

    return () => {
      track.removeEventListener("scroll", updateNavigation);
      window.removeEventListener("resize", updateNavigation);
    };
  }, [section.cards.length]);

  function scrollPage(direction: -1 | 1) {
    const track = trackRef.current;
    if (!track) return;

    track.scrollBy({ left: direction * track.clientWidth, behavior: "smooth" });
  }

  return (
    <section
      className="tns-home-journey-section"
      aria-labelledby={titleId}
      aria-busy={isLoading}
    >
      <header className="tns-home-journey-header">
        <div className="tns-home-journey-heading">
          <h2 id={titleId} className="tns-home-journey-title">
            {section.title}
          </h2>
          <p className="tns-home-journey-subtitle">{section.subtitle}</p>
        </div>

        <div className="tns-home-journey-actions">
          <NavLink
            to={section.actionHref}
            className="tns-home-journey-action"
            aria-label={section.actionLabel}
          >
            <span className="tns-home-journey-action-label">{section.actionLabel}</span>
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="m6 3 5 5-5 5" />
            </svg>
          </NavLink>
          <div
            className="tns-home-journey-navigation"
            role="group"
            aria-label={`${section.title} carousel navigation`}
          >
            <button
              type="button"
              aria-label={`Previous cards in ${section.title}`}
              aria-controls={trackId}
              disabled={!canScrollPrevious}
              onClick={() => scrollPage(-1)}
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="m10 3-5 5 5 5" />
              </svg>
            </button>
            <button
              type="button"
              aria-label={`Next cards in ${section.title}`}
              aria-controls={trackId}
              disabled={!canScrollNext}
              onClick={() => scrollPage(1)}
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="m6 3 5 5-5 5" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      <ul
        ref={trackRef}
        id={trackId}
        className="tns-home-journey-track"
        aria-label={isLoading ? "Loading scholarship opportunities" : `${section.title} cards`}
      >
        {isLoading
          ? Array.from({ length: 3 }, (_, index) => (
            <li key={`${section.id}-skeleton-${index}`} className="tns-home-journey-item">
              <article
                className="tns-home-journey-card tns-home-journey-card--skeleton"
                aria-hidden="true"
              >
                <div className="tns-home-journey-card__media scholarship-skeleton-block" />
                <div className="tns-home-journey-card__copy">
                  <div className="scholarship-skeleton-line" style={{ width: "85%", height: 20 }} />
                  <div className="scholarship-skeleton-line" style={{ width: "55%", height: 16 }} />
                </div>
              </article>
            </li>
          ))
          : section.cards.map((card) => (
          <li key={card.id} className="tns-home-journey-item">
            <HomepageJourneyCardView card={card} />
          </li>
          ))}
      </ul>
    </section>
  );
}
