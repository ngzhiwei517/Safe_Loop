import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { label: string };

function Button({ label, className = "", ...props }: ButtonProps) {
  return <button className={`min-h-14 w-full rounded-control px-5 text-base font-bold transition focus:outline-none focus:ring-2 focus:ring-primaryStrong ${className}`} {...props}>{label}</button>;
}

export function PrimaryButton(props: ButtonProps) { return <Button {...props} className={`bg-primary text-ink-inverse ${props.className ?? ""}`} />; }
export function SecondaryButton(props: ButtonProps) { return <Button {...props} className={`border border-border bg-surface text-ink ${props.className ?? ""}`} />; }
export function DestructiveButton(props: ButtonProps) { return <Button {...props} className={`bg-danger text-ink-inverse ${props.className ?? ""}`} />; }
