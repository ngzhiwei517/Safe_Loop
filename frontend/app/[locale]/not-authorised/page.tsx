import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { isLocale } from "../../../lib/locales";
import { SignOutButton } from "../../../components/auth/SignOutButton";

export default async function NotAuthorisedPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations({ locale });
  return <main className="mx-auto max-w-xl px-6 py-16"><h1 className="text-3xl font-bold">{t("app.notAuthorised.title")}</h1><p className="mt-4">{t("app.notAuthorised.detail")}</p><div className="mt-6"><SignOutButton variant="text" /></div></main>;
}
