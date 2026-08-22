import type { ReactNode } from "react";

export function EmptyState({ icon, title, detail, action }: { icon: ReactNode; title: string; detail: string; action?: ReactNode }) {
  return <div className="px-6 py-10 text-center text-inkMuted"><div className="mx-auto mb-3 grid h-16 w-16 place-items-center rounded-tile bg-surfaceSunken">{icon}</div><strong className="block text-lg text-ink">{title}</strong><p className="mt-1 text-base">{detail}</p>{action && <div className="mt-5">{action}</div>}</div>;
}
