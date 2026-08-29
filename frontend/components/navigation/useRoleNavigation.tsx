"use client";

import {
  BellIcon,
  BookOpenIcon,
  ChartBarIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
  HomeIcon,
  IdentificationIcon,
  LightBulbIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { useTranslations } from "next-intl";

import type { AppRole } from "../../lib/auth";
import type { NavigationItem } from "./BottomNavigation";

export function useRoleNavigation(
  locale: string,
  role: AppRole,
): NavigationItem[] {
  const t = useTranslations();
  const profile = {
    href: `/${locale}/profile`,
    label: t("app.profile"),
    icon: <IdentificationIcon className="h-5 w-5" />,
  };

  if (role === "reporter") {
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
      profile,
    ];
  }

  if (role === "reviewer") {
    return [
      {
        href: `/${locale}/review`,
        label: t("review.nav.queue"),
        icon: <ClipboardDocumentListIcon className="h-5 w-5" />,
      },
      {
        href: `/${locale}/documents`,
        label: t("review.nav.documents"),
        icon: <DocumentTextIcon className="h-5 w-5" />,
      },
      {
        href: `/${locale}/briefings`,
        label: t("review.nav.briefings"),
        icon: <BookOpenIcon className="h-5 w-5" />,
      },
      {
        href: `/${locale}/dashboard`,
        label: t("review.nav.dashboard"),
        icon: <ChartBarIcon className="h-5 w-5" />,
      },
      profile,
    ];
  }

  if (role === "admin") {
    return [
      {
        href: `/${locale}/documents`,
        label: t("review.nav.documents"),
        icon: <DocumentTextIcon className="h-5 w-5" />,
      },
      {
        href: `/${locale}/dashboard`,
        label: t("review.nav.dashboard"),
        icon: <ChartBarIcon className="h-5 w-5" />,
      },
      profile,
    ];
  }

  if (role === "responsible") {
    return [
      {
        href: `/${locale}/actions`,
        label: t("action.nav.myWork"),
        icon: <WrenchScrewdriverIcon className="h-5 w-5" />,
      },
      {
        href: `/${locale}/learn`,
        label: t("app.learn"),
        icon: <BookOpenIcon className="h-5 w-5" />,
      },
      profile,
    ];
  }

  return [
    {
      href: `/${locale}/learn`,
      label: t("app.learn"),
      icon: <BookOpenIcon className="h-5 w-5" />,
    },
    profile,
  ];
}
