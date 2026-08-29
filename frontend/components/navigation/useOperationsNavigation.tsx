import type { AppShellNavItem } from "../ui/AppShell";
import { useRoleNavigation } from "./useRoleNavigation";

export type OperationsRole = "reviewer" | "admin";

export function useOperationsNavigation(
  locale: string,
  role: OperationsRole = "reviewer",
): AppShellNavItem[] {
  return useRoleNavigation(locale, role);
}
