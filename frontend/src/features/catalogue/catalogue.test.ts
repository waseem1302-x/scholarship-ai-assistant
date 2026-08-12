import { describe, expect, it } from "vitest";

import { catalogueSearch, deadlineLabel, filtersFromSearch } from "./catalogue";

describe("catalogue query contract", () => {
  it("keeps open-now enabled and includes only selected structured filters", () => {
    const params = catalogueSearch(
      {
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
      "open_now=true&limit=20&offset=20&country=Malaysia&degree_level=masters&funding_type=full&field=Computer+Science",
    );
  });

  it("normalizes invalid URL values to the safe filter defaults", () => {
    expect(filtersFromSearch(new URLSearchParams("country=UK&limit=100&degree_level=unsupported"))).toEqual({
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
