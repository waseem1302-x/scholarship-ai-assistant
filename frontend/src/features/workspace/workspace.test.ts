import { describe, expect, it } from "vitest";

import { emptyProfileDraft } from "./types";
import { listFromText, profilePayload } from "./workspace";

describe("student workspace payloads", () => {
  it("does not send test scores when the student has not taken that test", () => {
    const payload = profilePayload({
      ...emptyProfileDraft,
      nationality: "Pakistani",
      english_test_status: "planned",
      ielts_score: "7.5",
      gre_status: "not_taken",
      gre_score: "320",
    });

    expect(payload.ielts_score).toBeNull();
    expect(payload.gre_score).toBeNull();
  });

  it("keeps completed test scores and comma-separated preferences structured", () => {
    const payload = profilePayload({
      ...emptyProfileDraft,
      english_test_status: "taken",
      ielts_score: "7.5",
      preferred_destination_countries: "Malaysia, Germany,  Canada ",
    });

    expect(payload.ielts_score).toBe(7.5);
    expect(payload.preferred_destination_countries).toEqual(["Malaysia", "Germany", "Canada"]);
  });

  it("removes empty list entries before a profile is saved", () => {
    expect(listFromText("paper one, , paper two,  ")).toEqual(["paper one", "paper two"]);
  });
});
