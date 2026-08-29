import type { NavigationItem } from "./BottomNavigation";
import { useRoleNavigation } from "./useRoleNavigation";

export function useReporterNavigation(locale: string): NavigationItem[] {
  return useRoleNavigation(locale, "reporter");
}
