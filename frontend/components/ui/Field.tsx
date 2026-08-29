import { useId, type InputHTMLAttributes, type ReactElement, type Ref, type TextareaHTMLAttributes } from "react";

type InputFieldProps = { label: string; error?: string; rows?: never } & InputHTMLAttributes<HTMLInputElement>;
type TextareaFieldProps = { label: string; error?: string; rows: number; inputRef?: Ref<HTMLTextAreaElement> } & TextareaHTMLAttributes<HTMLTextAreaElement>;
type FieldProps = InputFieldProps | TextareaFieldProps;

export function Field(props: TextareaFieldProps): ReactElement;
export function Field(props: InputFieldProps): ReactElement;

export function Field({ label, error, ...allProps }: FieldProps) {
  const { inputRef, ...props } = allProps as FieldProps & { inputRef?: Ref<HTMLTextAreaElement> };
  const generatedId = useId();
  const inputId = props.id ?? generatedId;
  const errorId = `${inputId}-error`;
  const describedBy = [props["aria-describedby"], error ? errorId : null]
    .filter(Boolean)
    .join(" ") || undefined;
  const accessibleProps = {
    ...props,
    id: inputId,
    "aria-describedby": describedBy,
    "aria-invalid": error ? true : props["aria-invalid"],
  };
  const inputClass = "mt-1 min-h-[52px] w-full rounded-control border border-border bg-surface px-4 text-base text-ink outline-none focus:border-primaryStrong focus:ring-2 focus:ring-primaryTint";
  return <label className="block text-sm font-bold text-inkMuted"><span>{label}</span>{"rows" in props ? <textarea ref={inputRef} className={`${inputClass} min-h-24 py-3`} {...accessibleProps as TextareaHTMLAttributes<HTMLTextAreaElement>} /> : <input className={inputClass} {...accessibleProps as InputHTMLAttributes<HTMLInputElement>} />}{error && <span className="mt-1 block text-sm text-danger" id={errorId}>{error}</span>}</label>;
}
