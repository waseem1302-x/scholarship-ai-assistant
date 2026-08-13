import { describe, expect, it, vi } from "vitest";

import { emptyProfileDraft, type StudentProfile } from "./types";
import { listFromText, profilePayload, saveProfile } from "./workspace";

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

  it("keeps target intake year structured for eligibility rules", () => {
    const payload = profilePayload({ ...emptyProfileDraft, target_intake_year: "2027" });

    expect(payload.target_intake_year).toBe(2027);
  });

  it("attaches expected_version only when saving an existing profile", async () => {
    const requests: unknown[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(init ? JSON.parse(String(init.body)) : null);
      return Promise.resolve(new Response(JSON.stringify({ version: 8 }), { status: 200, headers: { "Content-Type": "application/json" } }));
    }) as typeof fetch;
    const profile = { version: 7 } as StudentProfile;

    await saveProfile(emptyProfileDraft, profile);

    expect(requests[0]).toMatchObject({ expected_version: 7 });
    globalThis.fetch = originalFetch;
  });

  it("removes empty list entries before a profile is saved", () => {
    expect(listFromText("paper one, , paper two,  ")).toEqual(["paper one", "paper two"]);
  });
});
