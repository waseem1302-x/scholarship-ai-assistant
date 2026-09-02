import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  degreeOptions,
  filterDestinationOptions,
  fundingOptions,
  resolveDestinationOption,
  type ActivePopover,
  type DestinationOption,
  type HomeSearchState,
} from "../features/catalogue/searchOptions";
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
  const desktopCountryInputRef = useRef<HTMLInputElement>(null);
  const [highlightedDestination, setHighlightedDestination] = useState(-1);
  const [destinationError, setDestinationError] = useState<"desktop" | "mobile" | null>(null);
  const [mobileDestinationFocused, setMobileDestinationFocused] = useState(false);
  const isOpen = activePopover !== null;
  const destinationSuggestions = useMemo(
    () => filterDestinationOptions(search.country),
    [search.country],
  );

  function openPopover(popover: SearchPopover) {
    onPopoverChange(activePopover === popover ? null : popover);
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const typedCountry = search.country.trim();
    const resolvedDestination = resolveDestinationOption(typedCountry);
    if (typedCountry && !resolvedDestination) {
      const errorSource = event.currentTarget.classList.contains("tns-airbnb-search-pill") ? "desktop" : "mobile";
      setDestinationError(errorSource);
      onPopoverChange("where");
      if (errorSource === "desktop") {
        desktopCountryInputRef.current?.focus();
      } else {
        setMobileDestinationFocused(true);
      }
      return;
    }

    const country = resolvedDestination?.country ?? "";
    setDestinationError(null);
    onPopoverChange(null);
    if (country !== search.country) {
      onSearchChange((current) => ({ ...current, country }));
    }

    const params = new URLSearchParams();
    if (country) params.set("country", country);
    if (search.degree_level) params.set("degree_level", search.degree_level);
    if (search.funding_type) params.set("funding_type", search.funding_type);

    const query = params.toString();
    navigate(query ? `/catalogue?${query}` : "/catalogue");
  }

  function updateCountry(country: string) {
    setDestinationError(null);
    setHighlightedDestination(-1);
    onSearchChange((current) => ({ ...current, country }));
  }

  function selectDestination(destination: DestinationOption | null, advanceToDegree: boolean) {
    updateCountry(destination?.country ?? "");
    onPopoverChange(advanceToDegree ? "degree" : "where");
  }

  function handleDestinationKeyDown(event: React.KeyboardEvent<HTMLInputElement>, advanceToDegree: boolean) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      onPopoverChange("where");
      setHighlightedDestination((current) =>
        Math.min(current + 1, destinationSuggestions.length - 1),
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedDestination((current) => Math.max(current - 1, 0));
      return;
    }

    if (event.key === "Enter" && highlightedDestination >= 0) {
      event.preventDefault();
      selectDestination(destinationSuggestions[highlightedDestination], advanceToDegree);
      return;
    }

    if (event.key === "Escape") {
      onPopoverChange(null);
    }
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
        data-active-segment={activePopover ?? "none"}
        onSubmit={submit}
        role="search"
        aria-label="Search verified scholarships"
      >
        <span className="tns-active-segment-indicator" aria-hidden="true" />

        <div className="tns-search-field segment-where">
          <div
            className={`tns-airbnb-segment ${activePopover === "where" ? "is-active" : ""}`}
            onClick={() => {
              onPopoverChange("where");
              desktopCountryInputRef.current?.focus();
            }}
          >
            <span className="tns-segment-text-col">
              <label className="tns-segment-label" htmlFor="desktop-country-search">Destination</label>
              <input
                id="desktop-country-search"
                ref={desktopCountryInputRef}
                type="text"
                className={`tns-segment-input tns-destination-input ${search.country ? "is-filled" : ""}`}
                value={search.country}
                placeholder="Anywhere"
                autoComplete="off"
                role="combobox"
                aria-label="Search country"
                aria-autocomplete="list"
                aria-expanded={activePopover === "where"}
                aria-controls="desktop-destination-suggestions"
                aria-activedescendant={highlightedDestination >= 0 ? `desktop-destination-${highlightedDestination}` : undefined}
                aria-invalid={destinationError === "desktop"}
                aria-describedby={destinationError === "desktop" ? "desktop-destination-error" : undefined}
                onFocus={() => onPopoverChange("where")}
                onChange={(event) => updateCountry(event.target.value)}
                onKeyDown={(event) => handleDestinationKeyDown(event, true)}
              />
            </span>
            {search.country && (
              <button
                type="button"
                className="tns-destination-clear"
                aria-label="Clear destination"
                onMouseDown={(event) => event.preventDefault()}
                onClick={(event) => {
                  event.stopPropagation();
                  updateCountry("");
                  onPopoverChange("where");
                  desktopCountryInputRef.current?.focus();
                }}
              >
                <span aria-hidden="true">×</span>
              </button>
            )}
            <span className="tns-search-divider" aria-hidden="true" />
          </div>

          <div
            id="destination-popover"
            className={`tns-popover-panel tns-popover-where ${activePopover === "where" ? "is-open" : ""}`}
            role="dialog"
            aria-label="Popular scholarship destinations"
            aria-hidden={activePopover !== "where"}
            inert={activePopover !== "where"}
          >
              <h3 className="tns-popover-title">
                {search.country.trim() ? "Matching destinations" : "Popular scholarship destinations"}
              </h3>
              <div id="desktop-destination-suggestions" className="tns-region-grid" role="listbox" aria-label="Destination suggestions">
                {!search.country.trim() && (
                  <button
                    type="button"
                    className="tns-region-card"
                    role="option"
                    aria-selected={!search.country}
                    onClick={() => selectDestination(null, true)}
                  >
                    <span className="tns-region-copy">
                      <span className="tns-region-name">Anywhere</span>
                      <span className="tns-region-hint">Search every destination</span>
                    </span>
                  </button>
                )}
                {destinationSuggestions.map((destination, index) => (
                  <button
                    id={`desktop-destination-${index}`}
                    key={destination.country}
                    type="button"
                    className={`tns-region-card ${search.country === destination.country || highlightedDestination === index ? "is-selected" : ""}`}
                    role="option"
                    aria-label={destination.country}
                    aria-selected={search.country === destination.country || highlightedDestination === index}
                    onMouseEnter={() => setHighlightedDestination(index)}
                    onClick={() => selectDestination(destination, true)}
                  >
                    <span className="tns-region-copy">
                      <span className="tns-region-name">{destination.country}</span>
                      <span className="tns-region-hint">{destination.hint ?? "Scholarships in this destination"}</span>
                    </span>
                  </button>
                ))}
                {search.country.trim() && destinationSuggestions.length === 0 && (
                  <p className="tns-destination-empty">No matching destinations</p>
                )}
              </div>
              {destinationError === "desktop" && <p id="desktop-destination-error" className="tns-search-error" role="alert">Choose a destination from the suggestions.</p>}
          </div>
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

          <div
            id="degree-popover"
            className={`tns-popover-panel tns-popover-degree ${activePopover === "degree" ? "is-open" : ""}`}
            role="dialog"
            aria-label="Choose degree"
            aria-hidden={activePopover !== "degree"}
            inert={activePopover !== "degree"}
          >
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

          <div
            id="funding-popover"
            className={`tns-popover-panel tns-popover-funding ${activePopover === "funding" ? "is-open" : ""}`}
            role="dialog"
            aria-label="Choose funding"
            aria-hidden={activePopover !== "funding"}
            inert={activePopover !== "funding"}
          >
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

        <div className="tns-mobile-search-row">
          <span className="tns-mobile-search-field">
            <label className="tns-mobile-field-label" htmlFor="mobile-country-search">Where</label>
            <input
              id="mobile-country-search"
              type="text"
              className="tns-mobile-input"
              placeholder="Search destinations"
              value={search.country}
              autoComplete="off"
              role="combobox"
              aria-label="Search country"
              aria-autocomplete="list"
              aria-expanded={activePopover === "where"}
              aria-controls="mobile-destination-suggestions"
              aria-activedescendant={highlightedDestination >= 0 ? `mobile-destination-${highlightedDestination}` : undefined}
              aria-invalid={destinationError === "mobile"}
              aria-describedby={destinationError === "mobile" ? "mobile-destination-error" : undefined}
              onFocus={() => {
                setMobileDestinationFocused(true);
                onPopoverChange("where");
              }}
              onChange={(event) => {
                setMobileDestinationFocused(true);
                updateCountry(event.target.value);
                onPopoverChange("where");
              }}
              onKeyDown={(event) => handleDestinationKeyDown(event, false)}
            />
            {search.country && (
              <button
                type="button"
                className="tns-destination-clear tns-destination-clear--mobile"
                aria-label="Clear destination"
                onClick={() => {
                  updateCountry("");
                  setMobileDestinationFocused(true);
                  onPopoverChange("where");
                }}
              >
                <span aria-hidden="true">×</span>
              </button>
            )}
          </span>
        </div>

        <div
          id="mobile-destination-suggestions"
          className="tns-mobile-destination-suggestions"
          role="listbox"
          aria-label="Destination suggestions"
          aria-hidden={activePopover !== "where" || !mobileDestinationFocused}
          inert={activePopover !== "where" || !mobileDestinationFocused}
        >
          {!search.country.trim() && (
            <button type="button" role="option" aria-selected={!search.country} onClick={() => selectDestination(null, false)}>
              Anywhere
            </button>
          )}
          {destinationSuggestions.map((destination, index) => (
            <button
              id={`mobile-destination-${index}`}
              key={destination.country}
              type="button"
              role="option"
              aria-label={destination.country}
              aria-selected={search.country === destination.country || highlightedDestination === index}
              className={search.country === destination.country || highlightedDestination === index ? "is-selected" : ""}
              onClick={() => selectDestination(destination, false)}
            >
              {destination.country}
            </button>
          ))}
          {search.country.trim() && destinationSuggestions.length === 0 && (
            <p className="tns-destination-empty">No matching destinations</p>
          )}
        </div>
        {destinationError === "mobile" && <p id="mobile-destination-error" className="tns-search-error" role="alert">Choose a destination from the suggestions.</p>}

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
