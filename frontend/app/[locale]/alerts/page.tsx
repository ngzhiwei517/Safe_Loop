import { AlertsPage } from "../../../components/alerts/AlertsPage";
import { requireRole } from "../../../lib/auth";

export default async function AlertsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const { role } = await requireRole(locale, ["reviewer", "admin"]);
  return <AlertsPage requestedLocale={locale} role={role} />;
}
