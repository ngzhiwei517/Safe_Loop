import { ReviewDecisionPage } from "../../../../components/reports/ReviewDecisionPage";
import { requireRole } from "../../../../lib/auth";

export default async function ReviewerReportPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  await requireRole(locale, ["reviewer"]);
  return <ReviewDecisionPage id={id} requestedLocale={locale} />;
}
