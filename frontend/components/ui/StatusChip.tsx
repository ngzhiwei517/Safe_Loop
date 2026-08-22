import { statusColourMap, type ReportStatus } from "../../lib/stateMachine";

export function StatusChip({ status, label }: { status: ReportStatus; label: string }) {
  const [fill, text] = statusColourMap[status] ?? ["surfaceSunken", "inkMuted"];
  return <span className="inline-flex min-h-11 items-center rounded-chip px-3 text-sm font-bold" style={{ background: `var(--${fill})`, color: `var(--${text})` }}>{label}</span>;
}
