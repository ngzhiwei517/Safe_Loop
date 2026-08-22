import type { ReactNode } from "react";

export function PhotoStrip({ photos, addLabel, addIcon = null }: { photos: string[]; addLabel: string; addIcon?: ReactNode }) {
  return <div className="flex gap-2.5" aria-label={addLabel}>{photos.map((photo) => <img key={photo} className="h-[76px] w-[76px] rounded-tile object-cover" src={photo} alt="" />)}<button type="button" className="grid h-[76px] w-[76px] place-items-center rounded-tile border border-dashed border-border bg-surfaceSunken text-2xl text-inkMuted" aria-label={addLabel}>{addIcon}</button></div>;
}
