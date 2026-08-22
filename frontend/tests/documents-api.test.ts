import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { uploadDocument } from "../lib/documents";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));

describe("document API client", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("sends metadata and source as one multipart request", async () => {
    vi.mocked(apiFetch).mockResolvedValue({});
    const file = new File(["fixture"], "procedure.pdf", { type: "application/pdf" });

    await uploadDocument(
      {
        title: "Work at height method statement",
        docRef: "WSH-MS-014",
        revision: "3",
        effectiveFrom: "2026-07-01",
        file,
      },
      "test-token",
    );

    const request = vi.mocked(apiFetch).mock.calls[0];
    expect(request[0]).toBe("/documents");
    expect(request[1]).toBe("test-token");
    expect(request[2]?.method).toBe("POST");
    const body = request[2]?.body;
    expect(body).toBeInstanceOf(FormData);
    const fields = body as FormData;
    expect(fields.get("doc_ref")).toBe("WSH-MS-014");
    expect(fields.get("revision")).toBe("3");
    expect(fields.get("file")).toBe(file);
  });
});
