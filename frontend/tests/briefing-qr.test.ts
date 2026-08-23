import { describe, expect, it } from "vitest";

import { briefingPublicUrl } from "../lib/briefingQr";
import { locales } from "../lib/locales";

describe("briefing QR target", () => {
  it("keeps the active locale and URL-encodes the unguessable token", () => {
    expect(
      briefingPublicUrl("https://safe.example/", locales[1], "secure/token+value"),
    ).toBe("https://safe.example/zh-CN/b/secure%2Ftoken%2Bvalue");
  });
});
