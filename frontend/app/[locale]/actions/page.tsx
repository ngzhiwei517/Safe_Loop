import { ActionsPage } from "../../../components/actions/ActionsPage";
import { requireRole } from "../../../lib/auth";

export default async function ActionsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  await requireRole(locale, ["responsible"]);
  return <ActionsPage requestedLocale={locale} />;
}
