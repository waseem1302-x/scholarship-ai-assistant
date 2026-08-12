import { describe, expect, it } from "vitest";

import { jsonImportRows, reviewActions } from "./admin";

describe("administrator workspace contracts", () => {
  it("accepts direct rows and the API-shaped rows envelope for JSON imports", () => {
    expect(jsonImportRows('[{"name":"One"}]')).toEqual([{ name: "One" }]);
    expect(jsonImportRows('{"rows":[{"name":"Two"}]}')).toEqual([{ name: "Two" }]);
  });

  it("rejects malformed and non-row JSON before a privileged request is made", () => {
    expect(() => jsonImportRows("not json")).toThrow("Enter valid JSON");
    expect(() => jsonImportRows('{"rows":[]}')).toThrow("Add at least one");
    expect(() => jsonImportRows('{"name":"not a row list"}')).toThrow("rows array");
  });

  it("marks every state-changing review action except publication as requiring notes", () => {
    expect(reviewActions.find((action) => action.value === "publish")?.needsNotes).toBe(false);
    expect(reviewActions.filter((action) => action.value !== "publish").every((action) => action.needsNotes)).toBe(true);
  });
});
