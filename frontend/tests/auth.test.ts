import { beforeEach, describe, expect, it, vi } from "vitest";

import { requireProfile, requireRole } from "../lib/auth";

const authState = vi.hoisted(() => ({
  user: { id: "profile-id" } as { id: string } | null,
  role: "reviewer" as string | null,
}));
const redirectMock = vi.hoisted(() =>
  vi.fn((href: string): never => {
    throw new Error(`redirect:${href}`);
  }),
);

vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("../lib/supabase/server", () => ({
  createClient: async () => ({
    auth: {
      getUser: async () => ({ data: { user: authState.user } }),
    },
    from: () => ({
      select: () => ({
        eq: () => ({
          maybeSingle: async () => ({
            data: authState.role === null ? null : { role: authState.role },
          }),
        }),
      }),
    }),
  }),
}));

describe("route role guards", () => {
  beforeEach(() => {
    authState.user = { id: "profile-id" };
    authState.role = "reviewer";
    redirectMock.mockClear();
  });

  it("sends signed-out users to the locale login", async () => {
    authState.user = null;

    await expect(requireProfile("zh-CN")).rejects.toThrow(
      "redirect:/zh-CN/login",
    );
  });

  it("sends profiles with the wrong role to not-authorised", async () => {
    authState.role = "responsible";

    await expect(requireRole("en", ["reviewer"])).rejects.toThrow(
      "redirect:/en/not-authorised",
    );
  });

  it("returns a permitted role for the protected route", async () => {
    await expect(requireRole("en", ["reviewer"])).resolves.toEqual({
      role: "reviewer",
    });
  });
});
