"use client";

import {
  ArrowPathIcon,
  MicrophoneIcon,
  StopIcon,
  TrashIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { normalizedAudioMimeType, type AudioMimeType } from "../../lib/media";
import type { LiveRecordingSession, LiveTranscriptDraft } from "../../lib/live-transcription";

const recordingCapSeconds = 120;
const recorderMimeCandidates = [
  "audio/webm;codecs=opus",
  "audio/mp4",
  "audio/mpeg",
] as const;

export function formatRecordingTime(totalSeconds: number): string {
  const bounded = Math.max(0, Math.min(recordingCapSeconds, totalSeconds));
  const minutes = Math.floor(bounded / 60);
  const seconds = bounded % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function chooseRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return recorderMimeCandidates.find((mimeType) =>
    MediaRecorder.isTypeSupported(mimeType),
  );
}

function audioFileName(mimeType: AudioMimeType): string {
  const extension = mimeType === "audio/mpeg" ? "mp3" : mimeType.split("/")[1];
  return `safeloop-report-${Date.now()}.${extension}`;
}

type VoiceRecorderProps = {
  value: File | null;
  onChange: (file: File | null, liveResult?: Promise<LiveTranscriptDraft | null>) => void;
  startLive?: (stream: MediaStream) => Promise<LiveRecordingSession | null>;
};

export function VoiceRecorder({ value, onChange, startLive }: VoiceRecorderProps) {
  const t = useTranslations();
  const [supported, setSupported] = useState(false);
  const [recording, setRecording] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const liveSessionRef = useRef<LiveRecordingSession | null>(null);
  const liveResultRef = useRef<Promise<LiveTranscriptDraft | null> | undefined>(undefined);

  useEffect(() => {
    setSupported(
      typeof MediaRecorder !== "undefined"
      && Boolean(navigator.mediaDevices?.getUserMedia),
    );
  }, []);

  useEffect(() => {
    if (!value) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(value);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [value]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    liveSessionRef.current?.cancel();
  }, []);

  function stopRecording() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (liveSessionRef.current) {
      liveResultRef.current = liveSessionRef.current.finish();
      liveSessionRef.current = null;
    }
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMimeType = chooseRecorderMimeType();
      const recorder = preferredMimeType
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);
      const normalizedMimeType = normalizedAudioMimeType(
        recorder.mimeType || preferredMimeType || "",
      );
      if (!normalizedMimeType) {
        stream.getTracks().forEach((track) => track.stop());
        setSupported(false);
        onChange(null);
        return;
      }

      onChange(null);
      try {
        liveSessionRef.current = await startLive?.(stream) ?? null;
      } catch {
        liveSessionRef.current = null;
      }
      liveResultRef.current = undefined;
      chunksRef.current = [];
      streamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const chunks = chunksRef.current;
        chunksRef.current = [];
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        setRecording(false);
        if (chunks.length === 0) return;
        const blob = new Blob(chunks, { type: normalizedMimeType });
        onChange(
          new File([blob], audioFileName(normalizedMimeType), {
            type: normalizedMimeType,
            lastModified: Date.now(),
          }),
          liveResultRef.current,
        );
      };

      recorder.start(1000);
      startedAtRef.current = Date.now();
      setElapsedSeconds(0);
      setRecording(true);
      timerRef.current = window.setInterval(() => {
        const elapsed = Math.min(
          recordingCapSeconds,
          Math.floor((Date.now() - startedAtRef.current) / 1000),
        );
        setElapsedSeconds(elapsed);
        if (elapsed >= recordingCapSeconds) stopRecording();
      }, 250);
    } catch {
      setSupported(false);
      onChange(null);
    }
  }

  if (!supported) return null;

  return (
    <section className="rounded-card border border-border bg-surfaceSunken p-4">
      <div className="flex items-start gap-3">
        <MicrophoneIcon className="mt-0.5 h-6 w-6 shrink-0 text-primaryStrong" />
        <div>
          <h2 className="text-base font-bold">{t("report.voice.title")}</h2>
          <p className="mt-1 text-sm leading-5 text-inkMuted">
            {t("report.voice.storageNotice")}
          </p>
        </div>
      </div>

      {recording ? (
        <div className="mt-4 flex items-center justify-between gap-4 rounded-control border border-danger/30 bg-dangerTint px-4 py-3">
          <div aria-live="polite">
            <p className="font-bold text-dangerStrong">{t("report.voice.recording")}</p>
            <p className="font-mono text-lg font-bold">
              {t("report.voice.timer", {
                elapsed: formatRecordingTime(elapsedSeconds),
                limit: formatRecordingTime(recordingCapSeconds),
              })}
            </p>
          </div>
          <button
            type="button"
            className="grid min-h-12 min-w-12 place-items-center rounded-full bg-danger text-ink-inverse focus:outline-none focus:ring-2 focus:ring-dangerStrong"
            aria-label={t("report.voice.stop")}
            onClick={stopRecording}
          >
            <StopIcon className="h-6 w-6" />
          </button>
        </div>
      ) : value && previewUrl ? (
        <div className="mt-4 space-y-3">
          <audio className="w-full" controls preload="metadata" src={previewUrl}>
            {t("report.voice.playbackUnsupported")}
          </audio>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className="flex min-h-11 items-center justify-center gap-2 rounded-control border border-border bg-surface px-3 text-sm font-bold"
              onClick={() => void startRecording()}
            >
              <ArrowPathIcon className="h-5 w-5" />
              {t("report.voice.recordAgain")}
            </button>
            <button
              type="button"
              className="flex min-h-11 items-center justify-center gap-2 rounded-control border border-border bg-surface px-3 text-sm font-bold"
              onClick={() => onChange(null)}
            >
              <TrashIcon className="h-5 w-5" />
              {t("report.voice.remove")}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="mt-4 flex min-h-12 w-full items-center justify-center gap-2 rounded-control bg-primary px-4 font-bold text-ink-inverse focus:outline-none focus:ring-2 focus:ring-primaryStrong"
          onClick={() => void startRecording()}
        >
          <MicrophoneIcon className="h-6 w-6" />
          {t("report.voice.record")}
        </button>
      )}
    </section>
  );
}
