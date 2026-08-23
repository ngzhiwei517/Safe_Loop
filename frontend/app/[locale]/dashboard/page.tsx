import { DashboardPage } from "../../../components/metrics/DashboardPage";

export default async function MetricsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <DashboardPage requestedLocale={locale} />;
}
