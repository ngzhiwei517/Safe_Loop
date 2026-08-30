import { apiFetch } from "./api";
import type { TranscriptionResult } from "./transcription";

export type LiveTranscriptDraft = {
  sessionId: string;
  text: string;
  detectedLocale: string;
};

export type LiveRecordingSession = {
  finish: () => Promise<LiveTranscriptDraft | null>;
  cancel: () => void;
};

type StartOptions = {
  stream: MediaStream;
  accessToken: string;
  hintLocale: "zh-CN" | "en-SG";
  onInterim: (text: string) => void;
};

function websocketBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_BACKEND_WS_URL;
  if (configured) return configured.replace(/\/$/, "");
  const httpBase = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (httpBase?.startsWith("http")) return httpBase.replace(/^http/, "ws").replace(/\/$/, "");
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.hostname;
  const port = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"
    ? ":8000"
    : window.location.port ? `:${window.location.port}` : "";
  return `${protocol}//${host}${port}`;
}

function pcm16(samples: Float32Array, sourceRate: number): ArrayBuffer {
  const ratio = sourceRate / 16000;
  const length = Math.max(1, Math.floor(samples.length / ratio));
  const output = new Int16Array(length);
  for (let index = 0; index < length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.max(start + 1, Math.floor((index + 1) * ratio));
    let sum = 0;
    for (let source = start; source < end && source < samples.length; source += 1) {
      sum += samples[source];
    }
    const sample = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output.buffer;
}

export async function startLiveTranscription({
  stream,
  accessToken,
  hintLocale,
  onInterim,
}: StartOptions): Promise<LiveRecordingSession | null> {
  if (typeof AudioContext === "undefined" || typeof WebSocket === "undefined") return null;
  const { ticket } = await apiFetch<{ ticket: string }>(
    "/transcribe/live/ticket",
    accessToken,
    { method: "POST", body: JSON.stringify({ hint_locale: hintLocale }) },
  );
  const socket = new WebSocket(
    `${websocketBaseUrl()}/transcribe/live?ticket=${encodeURIComponent(ticket)}`,
  );
  socket.binaryType = "arraybuffer";
  const audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const silentGain = audioContext.createGain();
  silentGain.gain.value = 0;
  source.connect(processor);
  processor.connect(silentGain);
  silentGain.connect(audioContext.destination);

  let settled = false;
  let resolveResult: (value: LiveTranscriptDraft | null) => void = () => undefined;
  const result = new Promise<LiveTranscriptDraft | null>((resolve) => {
    resolveResult = resolve;
  });
  const settle = (value: LiveTranscriptDraft | null) => {
    if (settled) return;
    settled = true;
    resolveResult(value);
  };
  const ready = new Promise<boolean>((resolve) => {
    const timeout = window.setTimeout(() => resolve(false), 10000);
    socket.onmessage = (event) => {
      const message = JSON.parse(String(event.data)) as Record<string, string>;
      if (message.type === "ready") {
        window.clearTimeout(timeout);
        resolve(true);
      } else if (message.type === "interim" || message.type === "final") {
        onInterim(message.text ?? "");
      } else if (message.type === "complete") {
        settle({
          sessionId: message.session_id,
          text: message.text,
          detectedLocale: message.detected_locale || "und",
        });
      } else if (message.type === "failure") {
        settle(null);
      }
    };
    socket.onerror = () => {
      window.clearTimeout(timeout);
      resolve(false);
      settle(null);
    };
    socket.onclose = () => settle(null);
  });
  if (!await ready) {
    source.disconnect();
    processor.disconnect();
    silentGain.disconnect();
    await audioContext.close();
    socket.close();
    return null;
  }

  processor.onaudioprocess = (event) => {
    if (socket.readyState !== WebSocket.OPEN) return;
    socket.send(pcm16(event.inputBuffer.getChannelData(0), audioContext.sampleRate));
  };

  const disconnectAudio = () => {
    processor.onaudioprocess = null;
    source.disconnect();
    processor.disconnect();
    silentGain.disconnect();
    void audioContext.close();
  };
  return {
    finish: async () => {
      disconnectAudio();
      if (socket.readyState === WebSocket.OPEN) socket.send("end");
      const timeout = new Promise<null>((resolve) => window.setTimeout(() => resolve(null), 15000));
      return Promise.race([result, timeout]);
    },
    cancel: () => {
      disconnectAudio();
      socket.close();
      settle(null);
    },
  };
}

export function commitLiveTranscript(
  sessionId: string,
  mediaId: string,
  accessToken: string,
): Promise<TranscriptionResult> {
  return apiFetch<TranscriptionResult>("/transcribe/live/commit", accessToken, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, media_id: mediaId }),
  });
}
