"use client";

import {
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";

import type { AppShellNavItem } from "../ui/AppShell";

export type OperationsRole = "reviewer" | "admin";

export function useOperationsNavigation(
  locale: string,
  role: OperationsRole = "reviewer",
): AppShellNavItem[] {
  const t = useTranslations();
  const documents = {
    href: `/${locale}/documents`,
    label: t("review.nav.documents"),
    icon: <DocumentTextIcon className="h-5 w-5" />,
  };
  const dashboard = {
    href: `/${locale}/dashboard`,
    label: t("review.nav.dashboard"),
    icon: <ChartBarIcon className="h-5 w-5" />,
  };

  if (role === "admin") return [documents, dashboard];

  return [
    {
      href: `/${locale}/review`,
      label: t("review.nav.queue"),
      icon: <ClipboardDocumentListIcon className="h-5 w-5" />,
    },
    documents,
    {
      href: `/${locale}/briefings`,
      label: t("review.nav.briefings"),
      icon: <BookOpenIcon className="h-5 w-5" />,
    },
    dashboard,
  ];
}
