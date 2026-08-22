import type { SupabaseClient } from "@supabase/supabase-js";

import { apiFetch } from "./api";

export const mediaPhase = {
  original: "original",
  evidence: "evidence",
} as const;

export type MediaPhase = (typeof mediaPhase)[keyof typeof mediaPhase];

const imageMimeTypes = ["image/jpeg", "image/png", "image/webp"] as const;
type ImageMimeType = (typeof imageMimeTypes)[number];

const reportMediaBucket =
  process.env.NEXT_PUBLIC_REPORT_MEDIA_BUCKET ?? "report-media";
const maxImageDimension = 1600;
const maxImageBytes = 10 * 1024 * 1024;

export class MediaUploadError extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

export type DecodedImage = {
  width: number;
  height: number;
  render: (width: number, height: number, mimeType: ImageMimeType) => Promise<Blob>;
  close: () => void;
};

export type ImageDecoder = (file: File) => Promise<DecodedImage>;

export function scaledImageDimensions(
  width: number,
  height: number,
  maximum = maxImageDimension,
): { width: number; height: number } {
  const scale = Math.min(1, maximum / Math.max(width, height));
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

function isImageMimeType(value: string): value is ImageMimeType {
  return imageMimeTypes.some((mimeType) => mimeType === value);
}

async function decodeBrowserImage(file: File): Promise<DecodedImage> {
  const bitmap = await createImageBitmap(file);
  return {
    width: bitmap.width,
    height: bitmap.height,
    render: async (width, height, mimeType) => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) {
        throw new MediaUploadError("media_downscale_failed");
      }
      context.drawImage(bitmap, 0, 0, width, height);
      return new Promise<Blob>((resolve, reject) => {
        canvas.toBlob(
          (blob) => {
            if (blob) resolve(blob);
            else reject(new MediaUploadError("media_downscale_failed"));
          },
          mimeType,
          0.86,
        );
      });
    },
    close: () => bitmap.close(),
  };
}

export async function downscaleImage(
  file: File,
  maximum = maxImageDimension,
  decoder: ImageDecoder = decodeBrowserImage,
): Promise<File> {
  if (!isImageMimeType(file.type)) {
    throw new MediaUploadError("media_type_not_allowed");
  }
  const image = await decoder(file);
  try {
    const target = scaledImageDimensions(image.width, image.height, maximum);
    if (target.width === image.width && target.height === image.height) {
      return file;
    }
    const blob = await image.render(target.width, target.height, file.type);
    return new File([blob], file.name, {
      type: file.type,
      lastModified: file.lastModified,
    });
  } finally {
    image.close();
  }
}

export type RegisteredMedia = {
  id: string;
  report_id: string;
  storage_path: string;
  mime_type: string;
  phase: MediaPhase;
  caption: string | null;
};

export type ReportPhotoUpload = {
  client: SupabaseClient;
  file: File;
  userId: string;
  caption: string | null;
  phase?: MediaPhase;
  downscale?: (file: File) => Promise<File>;
};

type UploadOptions = ReportPhotoUpload & {
  reportId: string;
  accessToken: string;
};

function fileExtension(mimeType: ImageMimeType): string {
  if (mimeType === "image/jpeg") return "jpg";
  return mimeType.split("/")[1];
}

export async function uploadReportPhoto({
  client,
  file,
  userId,
  caption,
  phase = mediaPhase.original,
  reportId,
  accessToken,
  downscale = downscaleImage,
}: UploadOptions): Promise<RegisteredMedia> {
  const resized = await downscale(file);
  if (!isImageMimeType(resized.type)) {
    throw new MediaUploadError("media_type_not_allowed");
  }
  if (resized.size > maxImageBytes) {
    throw new MediaUploadError("media_too_large");
  }

  const storagePath = `${userId}/${reportId}/${crypto.randomUUID()}.${fileExtension(resized.type)}`;
  const bucket = client.storage.from(reportMediaBucket);
  const { error } = await bucket.upload(storagePath, resized, {
    contentType: resized.type,
    upsert: false,
  });
  if (error) {
    throw new MediaUploadError("media_upload_failed");
  }

  try {
    return await apiFetch<RegisteredMedia>(
      `/reports/${reportId}/media`,
      accessToken,
      {
        method: "POST",
        body: JSON.stringify({
          storage_path: storagePath,
          mime_type: resized.type,
          phase,
          caption,
        }),
      },
    );
  } catch (registrationError) {
    await bucket.remove([storagePath]);
    throw registrationError;
  }
}
