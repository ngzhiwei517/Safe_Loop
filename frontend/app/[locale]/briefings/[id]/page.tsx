import { BriefingEditorPage } from "../../../../components/briefings/BriefingEditorPage";
import { requireRole } from "../../../../lib/auth";

export default async function BriefingDetailPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  await requireRole(locale, ["reviewer"]);
  return <BriefingEditorPage id={id} requestedLocale={locale} />;
}
