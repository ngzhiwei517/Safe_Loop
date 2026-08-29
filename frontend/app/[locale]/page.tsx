import { redirect } from "next/navigation";

import { requireProfile } from "../../lib/auth";

export default async function LocaleHome({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const { role } = await requireProfile(locale);
  if (role === "reporter") redirect(`/${locale}/report/new`);
  if (role === "reviewer") redirect(`/${locale}/review`);
  if (role === "responsible") redirect(`/${locale}/actions`);
  if (role === "crew") redirect(`/${locale}/learn`);
  redirect(`/${locale}/dashboard`);
}
