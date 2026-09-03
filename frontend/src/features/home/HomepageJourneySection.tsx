import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import type {
  HomepageJourneyCard,
  HomepageJourneySectionContent,
} from "./homepageJourneyContent";
import "./homepage-journey.css";

interface HomepageJourneySectionProps {
  section: HomepageJourneySectionContent;
  savedFavorites: Set<string>;
  onToggleFavorite: (id: string) => void;
}

interface HomepageJourneyCardViewProps {
  card: HomepageJourneyCard;
  isSaved: boolean;
  onToggleFavorite: (id: string) => void;
}

function HomepageJourneyCardView({
  card,
  isSaved,
  onToggleFavorite,
}: HomepageJourneyCardViewProps) {
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

        {card.favoriteId ? (
          <button
            type="button"
            className={`tns-home-journey-card__favorite${isSaved ? " is-saved" : ""}`}
            aria-label={isSaved ? `Remove ${card.title} from saved` : `Save ${card.title}`}
            aria-pressed={isSaved}
            onClick={() => onToggleFavorite(card.favoriteId!)}
          >
            <svg viewBox="0 0 32 32" aria-hidden="true">
              <path d="M16 28.7C8.8 23.8 1.7 17.8 1.7 10.6c0-1.9.7-3.7 2.1-5.1a7.1 7.1 0 0 1 10.1 0L16 7.6l2.1-2.1a7.1 7.1 0 0 1 10.1 0c1.4 1.4 2.1 3.2 2.1 5.1 0 7.2-7.1 13.2-14.3 18.1Z" />
            </svg>
          </button>
        ) : null}
      </div>

      <div className="tns-home-journey-card__copy">
        <p className="tns-home-journey-card__eyebrow">{card.eyebrow}</p>
        <h3 id={titleId} className="tns-home-journey-card__title">
          <Link to={card.href}>{card.title}</Link>
        </h3>
        <p className="tns-home-journey-card__description">{card.description}</p>

        {card.sourceUrl ? (
          <div className="tns-home-journey-card__source">
            <a href={card.sourceUrl} target="_blank" rel="noreferrer">
              {`Official criteria for ${card.eyebrow}`}
            </a>
            {card.sourceReviewedAt ? <span>Reviewed {card.sourceReviewedAt}</span> : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function HomepageJourneySection({
  section,
  savedFavorites,
  onToggleFavorite,
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
      setCanScrollPrevious(track.scrollLeft > 1);
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
    <section className="tns-home-journey-section" aria-labelledby={titleId}>
      <header className="tns-home-journey-header">
        <div className="tns-home-journey-heading">
          <h2 id={titleId} className="tns-home-journey-title">
            {section.title}
          </h2>
          <p className="tns-home-journey-subtitle">{section.subtitle}</p>
        </div>

        <div className="tns-home-journey-actions">
          <NavLink to={section.actionHref} className="tns-home-journey-action">
            {section.actionLabel}
          </NavLink>
          <div
            className="tns-home-journey-navigation"
            aria-label={`${section.title} carousel navigation`}
          >
            <button
              type="button"
              aria-label="Previous"
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
              aria-label="Next"
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
        aria-label={`${section.title} cards`}
      >
        {section.cards.map((card) => (
          <li key={card.id} className="tns-home-journey-item">
            <HomepageJourneyCardView
              card={card}
              isSaved={card.favoriteId ? savedFavorites.has(card.favoriteId) : false}
              onToggleFavorite={onToggleFavorite}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
