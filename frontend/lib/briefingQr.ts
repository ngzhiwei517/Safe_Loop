import type { Locale } from "./locales";

const SHEET_WIDTH = 1240;
const SHEET_HEIGHT = 1754;
const QR_SIZE = 680;
const PDF_WIDTH = 595.28;
const PDF_HEIGHT = 841.89;
const FONT_STACK = '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif';

export type NoticeboardCopy = {
  title: string;
  instruction: string;
  reference: string;
  validity: string;
  footer: string;
};

export function briefingPublicUrl(
  origin: string,
  locale: Locale,
  token: string,
): string {
  return `${origin.replace(/\/$/, "")}/${locale}/b/${encodeURIComponent(token)}`;
}

export async function qrDataUrl(publicUrl: string): Promise<string> {
  const { default: QRCode } = await import("qrcode");
  return QRCode.toDataURL(publicUrl, {
    errorCorrectionLevel: "H",
    margin: 4,
    width: QR_SIZE,
  });
}

function loadImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("briefing_qr_image_failed"));
    image.src = source;
  });
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function wrappedLines(
  context: CanvasRenderingContext2D,
  value: string,
  maximumWidth: number,
): string[] {
  const characters = Array.from(value);
  const lines: string[] = [];
  let line = "";
  for (const character of characters) {
    const candidate = line + character;
    if (line && context.measureText(candidate).width > maximumWidth) {
      lines.push(line.trim());
      line = character;
    } else {
      line = candidate;
    }
  }
  if (line.trim()) lines.push(line.trim());
  return lines;
}

function drawCentredText(
  context: CanvasRenderingContext2D,
  value: string,
  y: number,
  maximumWidth: number,
  lineHeight: number,
): number {
  const lines = wrappedLines(context, value, maximumWidth);
  for (const [index, line] of lines.entries()) {
    context.fillText(line, SHEET_WIDTH / 2, y + index * lineHeight);
  }
  return y + lines.length * lineHeight;
}

async function noticeboardCanvas(
  publicUrl: string,
  copy: NoticeboardCopy,
): Promise<HTMLCanvasElement> {
  const canvas = document.createElement("canvas");
  canvas.width = SHEET_WIDTH;
  canvas.height = SHEET_HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("briefing_qr_canvas_unavailable");

  context.fillStyle = token("--surface");
  context.fillRect(0, 0, SHEET_WIDTH, SHEET_HEIGHT);
  context.fillStyle = token("--primary");
  context.fillRect(0, 0, SHEET_WIDTH, 44);
  context.fillStyle = token("--ink");
  context.textAlign = "center";
  context.textBaseline = "top";
  context.font = `700 68px ${FONT_STACK}`;
  let y = drawCentredText(context, copy.title, 116, 1020, 82);
  context.fillStyle = token("--ink-muted");
  context.font = `400 34px ${FONT_STACK}`;
  y = drawCentredText(context, copy.instruction, y + 28, 980, 48);

  const qrImage = await loadImage(await qrDataUrl(publicUrl));
  const qrX = (SHEET_WIDTH - QR_SIZE) / 2;
  const qrY = Math.max(430, y + 40);
  context.drawImage(qrImage, qrX, qrY, QR_SIZE, QR_SIZE);

  context.fillStyle = token("--ink");
  context.font = `700 34px ${FONT_STACK}`;
  y = drawCentredText(context, copy.reference, qrY + QR_SIZE + 48, 1040, 46);
  context.fillStyle = token("--ink-muted");
  context.font = `400 30px ${FONT_STACK}`;
  y = drawCentredText(context, copy.validity, y + 18, 1040, 42);
  context.font = `400 26px ${FONT_STACK}`;
  drawCentredText(context, copy.footer, Math.max(y + 42, 1580), 1040, 38);
  return canvas;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function canvasBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("briefing_qr_png_failed"));
    }, "image/png");
  });
}

export async function downloadNoticeboardPng(
  publicUrl: string,
  copy: NoticeboardCopy,
  filename: string,
): Promise<void> {
  const canvas = await noticeboardCanvas(publicUrl, copy);
  downloadBlob(await canvasBlob(canvas), `${filename}.png`);
}

export async function downloadNoticeboardPdf(
  publicUrl: string,
  copy: NoticeboardCopy,
  filename: string,
): Promise<void> {
  const canvas = await noticeboardCanvas(publicUrl, copy);
  const { PDFDocument } = await import("pdf-lib");
  const pdf = await PDFDocument.create();
  const page = pdf.addPage([PDF_WIDTH, PDF_HEIGHT]);
  const image = await pdf.embedPng(canvas.toDataURL("image/png"));
  page.drawImage(image, { x: 0, y: 0, width: PDF_WIDTH, height: PDF_HEIGHT });
  const bytes = await pdf.save();
  downloadBlob(new Blob([bytes], { type: "application/pdf" }), `${filename}.pdf`);
}
