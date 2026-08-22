import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lets the runtime set a multipart boundary", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(
        JSON.stringify({ ok: true }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const body = new FormData();
    body.set("file", new File(["fixture"], "procedure.pdf"));

    await apiFetch("/documents", "test-token", { method: "POST", body });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer test-token");
    expect(headers.has("Content-Type")).toBe(false);
  });
});
