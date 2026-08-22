import { statusColourMap, type ReportStatus } from "../../lib/stateMachine";

export type TimelineEvent = { id?: string; title: string; detail: string; note?: string; status?: ReportStatus; state?: "now" | "bad" | "todo" };

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return <ol>{events.map((event) => { const [fill, text] = event.status ? statusColourMap[event.status] : ["success-tint", "success-strong"]; return <li className="group grid grid-cols-[20px_1fr] gap-3 pb-5 last:pb-0" key={event.id ?? `${event.title}-${event.detail}`}><span className="relative flex justify-center"><span className="relative z-10 mt-0.5 h-[18px] w-[18px] rounded-full border-4" style={{ background: `var(--${fill})`, borderColor: `var(--${text})` }} /><span className="absolute bottom-[-20px] top-5 w-0.5 bg-border group-last:hidden" /></span><span><strong className="block text-base text-ink">{event.title}</strong><span className="block text-sm text-inkMuted">{event.detail}</span>{event.note && <span className="mt-1 block rounded-control bg-surfaceSunken px-3 py-2 text-sm text-ink">{event.note}</span>}</span></li>; })}</ol>;
}
