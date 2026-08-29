import { ReportDetail } from "../../../../components/reports/ReportDetail";
import { requireRole } from "../../../../lib/auth";

export default async function ReportSubmittedPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  await requireRole(locale, ["reporter"]);
  return <ReportDetail id={id} requestedLocale={locale} />;
}
