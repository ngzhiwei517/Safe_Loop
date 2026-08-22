export function LanguageSwitch({ current, options, onChange }: { current: string; options: { value: string; label: string }[]; onChange: (value: string) => void }) {
  return <div className="flex gap-2" aria-label={current}>{options.map((option) => <button type="button" key={option.value} onClick={() => onChange(option.value)} className={`min-h-11 rounded-chip px-3 text-sm font-bold ${option.value === current ? "bg-ink text-ink-inverse" : "border border-border bg-surface text-inkMuted"}`}>{option.label}</button>)}</div>;
}
