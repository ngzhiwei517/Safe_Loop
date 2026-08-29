import { LearnPage } from "../../../components/learning/LearnPage";
import { requireProfile } from "../../../lib/auth";

export default async function LearnRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const { role } = await requireProfile(locale);
  return <LearnPage requestedLocale={locale} role={role} />;
}
