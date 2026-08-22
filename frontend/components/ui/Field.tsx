import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

type FieldProps = { label: string; error?: string } & (InputHTMLAttributes<HTMLInputElement> | TextareaHTMLAttributes<HTMLTextAreaElement>);

export function Field({ label, error, ...props }: FieldProps) {
  const inputClass = "mt-1 min-h-[52px] w-full rounded-control border border-border bg-surface px-4 text-base text-ink outline-none focus:border-primaryStrong focus:ring-2 focus:ring-primaryTint";
  return <label className="block text-sm font-bold text-inkMuted"><span>{label}</span>{"rows" in props ? <textarea className={`${inputClass} min-h-24 py-3`} {...props as TextareaHTMLAttributes<HTMLTextAreaElement>} /> : <input className={inputClass} {...props as InputHTMLAttributes<HTMLInputElement>} />}{error && <span className="mt-1 block text-sm text-danger">{error}</span>}</label>;
}
