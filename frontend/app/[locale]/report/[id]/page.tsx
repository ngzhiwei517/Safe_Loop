import { ReportDetail } from "../../../../components/reports/ReportDetail";

export default async function ReportSubmittedPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  return <ReportDetail id={id} requestedLocale={locale} />;
}
