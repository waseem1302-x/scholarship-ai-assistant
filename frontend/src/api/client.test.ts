import { describe, expect, it } from "vitest";

import { readCsrfToken } from "./client";

describe("readCsrfToken", () => {
  it("returns the CSRF token without persisting sensitive state", () => {
    expect(readCsrfToken("theme=light; csrf_token=secure%2Dvalue; other=1")).toBe("secure%2Dvalue");
  });

  it("returns undefined when the cookie is unavailable", () => {
    expect(readCsrfToken("theme=light")).toBeUndefined();
  });
});
