import type { ReactNode } from "react";

export function Sheet({ title, children, closeLabel, closeIcon = null }: { title: string; children: ReactNode; closeLabel: string; closeIcon?: ReactNode }) {
  return <section className="rounded-t-card border border-border bg-surface p-5 shadow-safe" aria-label={title}><div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-bold">{title}</h2><button type="button" className="min-h-11 min-w-11 rounded-control border border-border" aria-label={closeLabel}>{closeIcon}</button></div>{children}</section>;
}
