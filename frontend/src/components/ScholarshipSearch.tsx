import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import {
  degreeOptions,
  fundingOptions,
  popularDestinations,
  type ActivePopover,
  type HomeSearchState,
} from "../features/home/HomePage";
import type { DegreeLevel, FundingType } from "../features/catalogue/types";

interface ScholarshipSearchProps {
  search: HomeSearchState;
  activePopover: ActivePopover;
  onSearchChange: (update: HomeSearchState | ((previous: HomeSearchState) => HomeSearchState)) => void;
  onPopoverChange: (popover: ActivePopover) => void;
}

type SearchPopover = Exclude<ActivePopover, null>;

export function ScholarshipSearch({
  search,
  activePopover,
  onSearchChange,
  onPopoverChange,
}: ScholarshipSearchProps) {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const isOpen = activePopover !== null;

  function openPopover(popover: SearchPopover) {
    onPopoverChange(activePopover === popover ? null : popover);
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onPopoverChange(null);

    const params = new URLSearchParams();
    if (search.country) params.set("country", search.country);
    if (search.degree_level) params.set("degree_level", search.degree_level);
    if (search.funding_type) params.set("funding_type", search.funding_type);

    const query = params.toString();
    navigate(query ? `/catalogue?${query}` : "/catalogue");
  }

  useEffect(() => {
    if (!activePopover) return;

    function closeOnOutsideClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        onPopoverChange(null);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onPopoverChange(null);
    }

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [activePopover, onPopoverChange]);

  const degreeLabel = search.degree_level
    ? degreeOptions.find((option) => option.value === search.degree_level)?.label ?? "Any degree"
    : "Any degree";
  const fundingLabel = search.funding_type
    ? fundingOptions.find((option) => option.value === search.funding_type)?.label ?? "Any funding"
    : "Any funding";

  return (
    <div className={`tns-search-container tns-premium-search ${isOpen ? "tns-search-container--open" : ""}`} ref={containerRef}>
      <div className="tns-mobile-airbnb-shell tns-mobile-premium-search">
        <button
          className="tns-mobile-start-search"
          type="button"
          onClick={() => openPopover("where")}
          aria-expanded={isOpen}
        >
          <span className="tns-mobile-start-icon" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </span>
          <span className="tns-mobile-start-copy">
            <strong>Start your search</strong>
            <small>Destination · Degree · Funding</small>
          </span>
        </button>

        <div className="tns-mobile-category-tabs" aria-label="Scholarship search shortcuts">
          <button
            type="button"
            className="tns-mobile-category-chip is-active"
            onClick={() => {
              onSearchChange({ country: "", degree_level: "", funding_type: "" });
              onPopoverChange(null);
            }}
          >
            All
          </button>
          <button type="button" className="tns-mobile-category-chip" onClick={() => openPopover("degree")}>
            Degree
          </button>
          <button type="button" className="tns-mobile-category-chip" onClick={() => openPopover("funding")}>
            Funding
          </button>
          <button type="button" className="tns-mobile-category-chip" onClick={() => openPopover("where")}>
            Country
          </button>
        </div>
      </div>

      <form
        className={`tns-airbnb-search-pill ${isOpen ? "has-active-segment" : ""}`}
        onSubmit={submit}
        role="search"
        aria-label="Search verified scholarships"
      >
        <div className="tns-search-field segment-where">
          <button
            type="button"
            className={`tns-airbnb-segment ${activePopover === "where" ? "is-active" : ""}`}
            onClick={() => openPopover("where")}
            aria-label={`Destination ${search.country || "Anywhere"}`}
            aria-expanded={activePopover === "where"}
            aria-controls="destination-popover"
            aria-haspopup="dialog"
          >
            <span className="tns-segment-text-col">
              <span className="tns-segment-label">Destination</span>
              <span className={`tns-segment-input ${search.country ? "is-filled" : ""}`}>
                {search.country || "Anywhere"}
              </span>
            </span>
            <span className="tns-search-divider" aria-hidden="true" />
          </button>

          {activePopover === "where" ? (
            <div
              id="destination-popover"
              className="tns-popover-panel tns-popover-where is-open"
              role="dialog"
              aria-label="Popular scholarship destinations"
            >
              <h3 className="tns-popover-title">Popular scholarship destinations</h3>
              <div className="tns-region-grid">
                <button
                  type="button"
                  className="tns-region-card"
                  aria-label="Anywhere"
                  onClick={() => {
                    onSearchChange((current) => ({ ...current, country: "" }));
                    onPopoverChange("degree");
                  }}
                >
                  <span className="tns-region-copy">
                    <span className="tns-region-name">Anywhere</span>
                    <span className="tns-region-hint">Search every destination</span>
                  </span>
                </button>
                {popularDestinations.map((destination) => (
                  <button
                    key={destination.country}
                    type="button"
                    className={`tns-region-card ${search.country === destination.country ? "is-selected" : ""}`}
                    aria-label={destination.country}
                    onClick={() => {
                      onSearchChange((current) => ({ ...current, country: destination.country }));
                      onPopoverChange("degree");
                    }}
                  >
                    <span className="tns-region-copy">
                      <span className="tns-region-name">{destination.country}</span>
                      <span className="tns-region-hint">{destination.hint}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="tns-search-field segment-degree">
          <button
            type="button"
            className={`tns-airbnb-segment ${activePopover === "degree" ? "is-active" : ""}`}
            onClick={() => openPopover("degree")}
            aria-label={`Degree ${degreeLabel}`}
            aria-expanded={activePopover === "degree"}
            aria-controls="degree-popover"
            aria-haspopup="dialog"
          >
            <span className="tns-segment-text-col">
              <span className="tns-segment-label">Degree</span>
              <span className={`tns-segment-input ${search.degree_level ? "is-filled" : ""}`}>
                {degreeLabel}
              </span>
            </span>
            <span className="tns-search-divider" aria-hidden="true" />
          </button>

          {activePopover === "degree" ? (
            <div id="degree-popover" className="tns-popover-panel tns-popover-degree is-open" role="dialog" aria-label="Choose degree">
              <h3 className="tns-popover-title">Choose degree</h3>
              <div className="tns-popover-list">
                {degreeOptions.map((option) => (
                  <button
                    key={option.value || "any"}
                    type="button"
                    className={`tns-popover-row ${search.degree_level === option.value ? "is-selected" : ""}`}
                    aria-label={option.value ? option.label : "Any degree"}
                    onClick={() => {
                      onSearchChange((current) => ({ ...current, degree_level: option.value }));
                      onPopoverChange("funding");
                    }}
                  >
                    <span className="tns-popover-row-text">
                      <span className="tns-popover-row-title">{option.value ? option.label : "Any degree"}</span>
                      <span className="tns-popover-row-desc">{option.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="tns-search-field segment-funding">
          <button
            type="button"
            className={`tns-airbnb-segment ${activePopover === "funding" ? "is-active" : ""}`}
            onClick={() => openPopover("funding")}
            aria-label={`Funding ${fundingLabel}`}
            aria-expanded={activePopover === "funding"}
            aria-controls="funding-popover"
            aria-haspopup="dialog"
          >
            <span className="tns-segment-text-col">
              <span className="tns-segment-label">Funding</span>
              <span className={`tns-segment-input ${search.funding_type ? "is-filled" : ""}`}>
                {fundingLabel}
              </span>
            </span>
          </button>

          {activePopover === "funding" ? (
            <div id="funding-popover" className="tns-popover-panel tns-popover-funding is-open" role="dialog" aria-label="Choose funding">
              <h3 className="tns-popover-title">Choose funding</h3>
              <div className="tns-popover-list">
                {fundingOptions.map((option) => (
                  <button
                    key={option.value || "any"}
                    type="button"
                    className={`tns-popover-row ${search.funding_type === option.value ? "is-selected" : ""}`}
                    aria-label={option.value ? option.label : "Any funding"}
                    onClick={() => {
                      onSearchChange((current) => ({ ...current, funding_type: option.value }));
                      onPopoverChange(null);
                    }}
                  >
                    <span className="tns-popover-row-text">
                      <span className="tns-popover-row-title">{option.value ? option.label : "Any funding"}</span>
                      <span className="tns-popover-row-desc">{option.desc}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <button type="submit" className="tns-search-submit-btn" aria-label="Search scholarships">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span className="tns-search-btn-text">Search</span>
        </button>
      </form>

      <form
        className={`tns-mobile-search-card ${isOpen ? "tns-mobile-search-card--open" : ""}`}
        onSubmit={submit}
        role="dialog"
        aria-label="Scholarship search"
      >
        <div className="tns-mobile-sheet-top">
          <div>
            <span className="tns-mobile-sheet-kicker">Scholarship search</span>
            <h3>Find the right opportunity</h3>
          </div>
          <button type="button" className="tns-mobile-sheet-close" onClick={() => onPopoverChange(null)} aria-label="Close scholarship search">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
              <line x1="6" y1="6" x2="18" y2="18" />
              <line x1="18" y1="6" x2="6" y2="18" />
            </svg>
          </button>
        </div>

        <label className="tns-mobile-search-row">
          <span className="tns-mobile-search-field">
            <span className="tns-mobile-field-label">Where</span>
            <input
              type="text"
              className="tns-mobile-input"
              placeholder="Search destinations"
              value={search.country}
              onChange={(event) => onSearchChange((current) => ({ ...current, country: event.target.value }))}
            />
          </span>
        </label>

        <label className="tns-mobile-search-row">
          <span className="tns-mobile-search-field">
            <span className="tns-mobile-field-label">Degree</span>
            <select
              className="tns-mobile-select"
              value={search.degree_level}
              onChange={(event) => onSearchChange((current) => ({ ...current, degree_level: event.target.value as DegreeLevel | "" }))}
            >
              <option value="">Any degree</option>
              {degreeOptions.filter((option) => option.value).map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </span>
        </label>

        <label className="tns-mobile-search-row">
          <span className="tns-mobile-search-field">
            <span className="tns-mobile-field-label">Funding</span>
            <select
              className="tns-mobile-select"
              value={search.funding_type}
              onChange={(event) => onSearchChange((current) => ({ ...current, funding_type: event.target.value as FundingType | "" }))}
            >
              <option value="">Any funding</option>
              {fundingOptions.filter((option) => option.value).map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </span>
        </label>

        <button type="submit" className="tns-mobile-search-btn">
          Search scholarships
        </button>
      </form>
    </div>
  );
}
