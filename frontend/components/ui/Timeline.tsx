export type TimelineEvent = { title: string; detail: string; state?: "now" | "bad" | "todo" };

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return <ol className="relative pl-8">{events.map((event) => <li className="relative pb-5 last:pb-0 before:absolute before:-left-8 before:top-1 before:h-[18px] before:w-[18px] before:rounded-full before:border-4 before:border-bg before:bg-success last:after:hidden after:absolute after:-left-[23px] after:top-6 after:bottom-0 after:w-0.5 after:bg-border" key={`${event.title}-${event.detail}`}><strong className="block text-base text-ink">{event.title}</strong><span className="text-sm text-inkMuted">{event.detail}</span></li>)}</ol>;
}
