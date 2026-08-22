import type { ReactNode } from "react";

export function Banner({ tone, title, detail, children }: { tone: "info" | "warning" | "urgent"; title: string; detail: string; children?: ReactNode }) {
  const styles = tone === "urgent" ? "bg-danger text-ink-inverse" : tone === "warning" ? "border border-border bg-warningTint text-warning" : "bg-primaryTint text-primaryStrong";
  return <aside className={`rounded-card p-4 ${styles}`}><strong className="block text-base">{title}</strong><span className="block text-sm opacity-90">{detail}</span>{children}</aside>;
}
