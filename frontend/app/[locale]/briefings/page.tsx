import { BriefingsPage } from "../../../components/briefings/BriefingsPage";

export default async function BriefingListPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <BriefingsPage requestedLocale={locale} />;
}
