import { apiFetch } from "./api";

export type TranscriptionResult = {
  transcript_id: string;
  text: string;
  detected_locale: string;
  confidence: number;
  duration_ms: number;
  provider: string;
  model: string;
  provider_ref: string;
  latency_ms: number;
  meets_confidence_threshold: boolean;
};

export function transcribeAudio(
  mediaId: string,
  hintLocale: "zh-CN" | "en-SG",
  accessToken: string,
): Promise<TranscriptionResult> {
  return apiFetch<TranscriptionResult>("/transcribe", accessToken, {
    method: "POST",
    body: JSON.stringify({ media_id: mediaId, hint_locale: hintLocale }),
  });
}
