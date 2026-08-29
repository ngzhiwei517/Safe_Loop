import { ReporterReportsPage } from "../../../components/reports/ReporterReportsPage";
import { requireRole } from "../../../lib/auth";

export default async function ReporterReportsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  await requireRole(locale, ["reporter"]);
  return <ReporterReportsPage requestedLocale={locale} />;
}
