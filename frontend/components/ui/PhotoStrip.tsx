import type { ReactNode } from "react";

export type PhotoStripItem = { src: string; alt: string };

export function PhotoStrip({ photos, addLabel, addIcon = null }: { photos: readonly (string | PhotoStripItem)[]; addLabel?: string; addIcon?: ReactNode }) {
  return <div className="flex gap-2.5 overflow-x-auto" aria-label={addLabel}>{photos.map((photo) => { const item = typeof photo === "string" ? { src: photo, alt: "" } : photo; return <img key={item.src} className="h-[76px] w-[76px] flex-none rounded-tile object-cover" src={item.src} alt={item.alt} />; })}{addLabel && <button type="button" className="grid h-[76px] w-[76px] flex-none place-items-center rounded-tile border border-dashed border-border bg-surfaceSunken text-2xl text-inkMuted" aria-label={addLabel}>{addIcon}</button>}</div>;
}
