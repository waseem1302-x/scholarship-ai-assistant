import { describe, expect, it } from "vitest";

import {
  catalogueSearch,
  deadlineLabel,
  filtersFromSearch,
} from "./catalogue";
import { defaultCatalogueFilters } from "./types";

describe("catalogue query contract", () => {
  it("keeps open-now enabled and includes only selected structured filters", () => {
    const params = catalogueSearch(
      {
        availability: "open",
        country: "Malaysia",
        degree_level: "masters",
        funding_type: "full",
        field: "Computer Science",
        nationality: "",
        limit: "20",
      },
      20,
    );

    expect(params.toString()).toBe(
      "availability=open&limit=20&offset=20&open_now=true&country=Malaysia&degree_level=masters&funding_type=full&field=Computer+Science",
    );
  });

  it("uses the upcoming state filter or no window filter for all verified records", () => {
    const upcoming = catalogueSearch({ ...defaultCatalogueFilters, availability: "upcoming" });
    const all = catalogueSearch({ ...defaultCatalogueFilters, availability: "all" });

    expect(upcoming.toString()).toBe(
      "availability=upcoming&limit=10&offset=0&application_window_state=upcoming",
    );
    expect(all.toString()).toBe("availability=all&limit=10&offset=0");
  });

  it("normalizes invalid URL values to all verified by default", () => {
    expect(filtersFromSearch(new URLSearchParams("country=UK&limit=100&degree_level=unsupported"))).toEqual({
      availability: "all",
      country: "UK",
      degree_level: "",
      funding_type: "",
      field: "",
      nationality: "",
      limit: "10",
    });
  });

  it("presents unknown and close deadlines without declaring an opportunity open", () => {
    expect(deadlineLabel(null)).toBe("Deadline varies");
    expect(deadlineLabel(new Date(Date.now() + 86_400_000).toISOString())).toBe("1 days left");
  });
});
