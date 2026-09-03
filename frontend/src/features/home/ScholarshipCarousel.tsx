import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import "./scholarship-carousel.css";

export interface ScholarshipCarouselItem {
  id: string;
  name: string;
  country: string;
  flag: string;
  degreeLevel: string;
  deadline: string;
  badge: string;
  guestBadge?: string;
  href: string;
  imageUrl: string;
  imagePosition?: string;
}

interface ScholarshipCarouselProps {
  id: string;
  title: string;
  items: ScholarshipCarouselItem[];
  savedFavorites: Set<string>;
  onToggleFavorite: (id: string) => void;
}

export function ScholarshipCarousel({
  id,
  title,
  items,
  savedFavorites,
  onToggleFavorite,
}: ScholarshipCarouselProps) {
  const titleId = `${id}-title`;
  const trackId = `${id}-track`;
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
  }, [items.length]);

  function scrollPage(direction: -1 | 1) {
    const track = trackRef.current;
    if (!track) return;

    track.scrollBy({ left: direction * track.clientWidth, behavior: "smooth" });
  }

  return (
    <section className="tns-opportunity-carousel" aria-labelledby={titleId}>
      <div className="tns-opportunity-carousel__header">
        <NavLink to="/catalogue" className="tns-opportunity-carousel__title-link">
          <h2 id={titleId}>{title}</h2>
          <span className="tns-opportunity-carousel__title-arrow" aria-hidden="true">
            <svg viewBox="0 0 16 16">
              <path d="m6 3 5 5-5 5" />
            </svg>
          </span>
        </NavLink>

        <div className="tns-opportunity-carousel__navigation" aria-label={`${title} carousel navigation`}>
          <button
            type="button"
            aria-label="Previous"
            aria-controls={trackId}
            disabled={!canScrollPrevious}
            onClick={() => scrollPage(-1)}
          >
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m10 3-5 5 5 5" /></svg>
          </button>
          <button
            type="button"
            aria-label="Next"
            aria-controls={trackId}
            disabled={!canScrollNext}
            onClick={() => scrollPage(1)}
          >
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>
          </button>
        </div>
      </div>

      <ul
        ref={trackRef}
        id={trackId}
        className="tns-opportunity-carousel__track"
        aria-label={`${title} scholarships`}
      >
        {items.map((item) => {
          const isSaved = savedFavorites.has(item.id);

          return (
            <li key={item.id} className="tns-opportunity-carousel__item">
              <article className="tns-scholarship-carousel-card">
                <div className="tns-scholarship-carousel-card__media">
                  <Link to={item.href} aria-label={item.name} className="tns-scholarship-carousel-card__image-link">
                    <img
                      src={item.imageUrl}
                      alt=""
                      loading="lazy"
                      decoding="async"
                      style={{ objectPosition: item.imagePosition ?? "center" }}
                    />
                  </Link>
                  <span className="tns-scholarship-carousel-card__badge">{item.badge}</span>
                  <button
                    type="button"
                    className={`tns-scholarship-carousel-card__favorite${isSaved ? " is-saved" : ""}`}
                    aria-label={isSaved ? `Remove ${item.name} from saved` : `Save ${item.name}`}
                    aria-pressed={isSaved}
                    onClick={() => onToggleFavorite(item.id)}
                  >
                    <svg viewBox="0 0 32 32" aria-hidden="true">
                      <path d="M16 28.7C8.8 23.8 1.7 17.8 1.7 10.6c0-1.9.7-3.7 2.1-5.1a7.1 7.1 0 0 1 10.1 0L16 7.6l2.1-2.1a7.1 7.1 0 0 1 10.1 0c1.4 1.4 2.1 3.2 2.1 5.1 0 7.2-7.1 13.2-14.3 18.1Z" />
                    </svg>
                  </button>
                </div>

                <div className="tns-scholarship-carousel-card__copy">
                  <h3>
                    <Link to={item.href}>{item.name}</Link>
                  </h3>
                  <p>
                    <span>{item.flag} {item.country}</span>
                    <span aria-hidden="true">·</span>
                    <span>{item.degreeLevel}</span>
                    <span aria-hidden="true">·</span>
                    <span>{item.deadline}</span>
                  </p>
                </div>
              </article>
            </li>
          );
        })}

        <li className="tns-opportunity-carousel__item">
          <NavLink to="/catalogue" className="tns-opportunity-carousel__see-all" aria-label={`See all ${title}`}>
            <span>See all</span>
            <span aria-hidden="true">→</span>
          </NavLink>
        </li>
      </ul>
    </section>
  );
}
