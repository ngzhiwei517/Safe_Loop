import { BriefingEditorPage } from "../../../../components/briefings/BriefingEditorPage";

export default async function BriefingDetailPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <BriefingEditorPage id={id} requestedLocale={locale} />;
}
