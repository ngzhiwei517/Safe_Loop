import { beforeEach, describe, expect, it, vi } from "vitest";

import { signOut } from "../app/[locale]/auth/actions";

const signOutMock = vi.hoisted(() => vi.fn());
const redirectMock = vi.hoisted(() =>
  vi.fn((href: string): never => {
    throw new Error(`redirect:${href}`);
  }),
);

vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("../lib/supabase/server", () => ({
  createClient: async () => ({ auth: { signOut: signOutMock } }),
}));

describe("signOut", () => {
  beforeEach(() => {
    signOutMock.mockReset();
    signOutMock.mockResolvedValue({ error: null });
    redirectMock.mockClear();
  });

  it("clears the session and returns to the localized login page", async () => {
    await expect(signOut("zh-CN")).rejects.toThrow("redirect:/zh-CN/login");
    expect(signOutMock).toHaveBeenCalledOnce();
  });

  it("does not redirect when Supabase cannot clear the session", async () => {
    signOutMock.mockResolvedValue({ error: new Error("offline") });
    await expect(signOut("en")).rejects.toThrow("sign_out_failed");
    expect(redirectMock).not.toHaveBeenCalled();
  });
});
