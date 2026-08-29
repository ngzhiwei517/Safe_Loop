import { ReportFlow } from "../../../../components/reports/ReportFlow";
import { requireRole } from "../../../../lib/auth";

export default async function NewReportPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  await requireRole(locale, ["reporter"]);
  return <ReportFlow />;
}
