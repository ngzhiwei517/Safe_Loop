import type { InputHTMLAttributes, ReactElement, TextareaHTMLAttributes } from "react";

type InputFieldProps = { label: string; error?: string; rows?: never } & InputHTMLAttributes<HTMLInputElement>;
type TextareaFieldProps = { label: string; error?: string; rows: number } & TextareaHTMLAttributes<HTMLTextAreaElement>;
type FieldProps = InputFieldProps | TextareaFieldProps;

export function Field(props: TextareaFieldProps): ReactElement;
export function Field(props: InputFieldProps): ReactElement;

export function Field({ label, error, ...props }: FieldProps) {
  const inputClass = "mt-1 min-h-[52px] w-full rounded-control border border-border bg-surface px-4 text-base text-ink outline-none focus:border-primaryStrong focus:ring-2 focus:ring-primaryTint";
  return <label className="block text-sm font-bold text-inkMuted"><span>{label}</span>{"rows" in props ? <textarea className={`${inputClass} min-h-24 py-3`} {...props as TextareaHTMLAttributes<HTMLTextAreaElement>} /> : <input className={inputClass} {...props as InputHTMLAttributes<HTMLInputElement>} />}{error && <span className="mt-1 block text-sm text-danger">{error}</span>}</label>;
}
