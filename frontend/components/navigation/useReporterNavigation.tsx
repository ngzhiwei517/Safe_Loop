"use client";

import {
  BellIcon,
  ClipboardDocumentListIcon,
  HomeIcon,
  LightBulbIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";

import type { NavigationItem } from "./BottomNavigation";

export function useReporterNavigation(locale: string): NavigationItem[] {
  const t = useTranslations();

  return [
    {
      href: `/${locale}/report/new`,
      label: t("app.home"),
      icon: <HomeIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/reports`,
      label: t("app.myReports"),
      icon: <ClipboardDocumentListIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/learn`,
      label: t("app.learn"),
      icon: <LightBulbIcon className="h-5 w-5" />,
    },
    {
      href: `/${locale}/inbox`,
      label: t("app.inbox"),
      icon: <BellIcon className="h-5 w-5" />,
    },
  ];
}
