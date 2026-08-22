import type { SupabaseClient } from "@supabase/supabase-js";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import {
  downscaleImage,
  mediaPhase,
  scaledImageDimensions,
  uploadReportPhoto,
  type ImageDecoder,
} from "../lib/media";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));

describe("report media", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("limits the longest image edge to 1600 pixels", async () => {
    expect(scaledImageDimensions(3200, 1200)).toEqual({ width: 1600, height: 600 });
    const render = vi.fn(async () => new Blob(["resized"], { type: "image/jpeg" }));
    const close = vi.fn();
    const decoder: ImageDecoder = async () => ({
      width: 3200,
      height: 1200,
      render,
      close,
    });
    const original = new File(["original"], "hazard.jpg", { type: "image/jpeg" });

    const resized = await downscaleImage(original, 1600, decoder);

    expect(render).toHaveBeenCalledWith(1600, 600, "image/jpeg");
    expect(resized.name).toBe(original.name);
    expect(resized.type).toBe(original.type);
    expect(close).toHaveBeenCalledOnce();
  });

  it("uploads with the user token client before registering the object", async () => {
    const upload = vi.fn(async (_path: string, _file: File, _options: object) => ({ data: {}, error: null }));
    const remove = vi.fn(async (_paths: string[]) => ({ data: [], error: null }));
    const from = vi.fn(() => ({ upload, remove }));
    const client = { storage: { from } } as unknown as SupabaseClient;
    vi.mocked(apiFetch).mockResolvedValue({
      id: "media-id",
      report_id: "report-id",
      storage_path: "path",
      mime_type: "image/jpeg",
      phase: mediaPhase.original,
      caption: null,
    });
    const photo = new File(["photo"], "hazard.jpg", { type: "image/jpeg" });

    await uploadReportPhoto({
      client,
      file: photo,
      userId: "reporter-id",
      reportId: "report-id",
      accessToken: "test-token",
      caption: null,
      downscale: async (file) => file,
    });

    expect(from).toHaveBeenCalledWith("report-media");
    const storagePath = upload.mock.calls[0][0];
    expect(storagePath).toMatch(/^reporter-id\/report-id\/[0-9a-f-]+\.jpg$/);
    expect(upload).toHaveBeenCalledWith(
      storagePath,
      photo,
      { contentType: "image/jpeg", upsert: false },
    );
    expect(apiFetch).toHaveBeenCalledWith(
      "/reports/report-id/media",
      "test-token",
      {
        method: "POST",
        body: JSON.stringify({
          storage_path: storagePath,
          mime_type: "image/jpeg",
          phase: mediaPhase.original,
          caption: null,
        }),
      },
    );
    expect(upload.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(apiFetch).mock.invocationCallOrder[0],
    );
    expect(remove).not.toHaveBeenCalled();
  });

  it("removes an orphaned upload when backend registration fails", async () => {
    const upload = vi.fn(async (_path: string, _file: File, _options: object) => ({ data: {}, error: null }));
    const remove = vi.fn(async (_paths: string[]) => ({ data: [], error: null }));
    const client = {
      storage: { from: () => ({ upload, remove }) },
    } as unknown as SupabaseClient;
    vi.mocked(apiFetch).mockRejectedValue(new Error("registration failed"));

    let caught: unknown;
    try {
      await uploadReportPhoto({
        client,
        file: new File(["photo"], "hazard.png", { type: "image/png" }),
        userId: "reporter-id",
        reportId: "report-id",
        accessToken: "test-token",
        caption: null,
        downscale: async (file) => file,
      });
    } catch (error) {
      caught = error;
    }

    expect(caught).toEqual(new Error("registration failed"));
    expect(remove).toHaveBeenCalledWith([expect.stringMatching(/^reporter-id\/report-id\//)]);
  });
});
