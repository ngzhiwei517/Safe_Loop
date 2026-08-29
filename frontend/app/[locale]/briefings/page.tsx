import { BriefingsPage } from "../../../components/briefings/BriefingsPage";
import { requireRole } from "../../../lib/auth";

export default async function BriefingListPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  await requireRole(locale, ["reviewer"]);
  return <BriefingsPage requestedLocale={locale} />;
}
