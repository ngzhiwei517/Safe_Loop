import { ReviewDecisionPage } from "../../../../components/reports/ReviewDecisionPage";

export default async function ReviewerReportPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <ReviewDecisionPage id={id} requestedLocale={locale} />;
}
