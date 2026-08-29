import { DashboardPage } from "../../../components/metrics/DashboardPage";
import { requireRole } from "../../../lib/auth";

export default async function MetricsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const { role } = await requireRole(locale, ["reviewer", "admin"]);
  return <DashboardPage requestedLocale={locale} role={role} />;
}
