import type { ReactNode } from "react";

export function IconTile({ children, tone = "primary" }: { children: ReactNode; tone?: "primary" | "success" | "warning" | "danger" }) {
  const styles = {
    primary: "bg-primaryTint text-primaryStrong",
    success: "bg-successTint text-successStrong",
    warning: "bg-warningTint text-warning",
    danger: "bg-dangerTint text-dangerStrong",
  } as const;

  return <span className={`grid h-12 w-12 place-items-center rounded-tile text-xl font-bold ${styles[tone]}`} aria-hidden="true">{children}</span>;
}
