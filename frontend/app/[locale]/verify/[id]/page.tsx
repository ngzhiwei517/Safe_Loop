import { VerificationPage } from "../../../../components/reports/VerificationPage";
import { requireRole } from "../../../../lib/auth";

export default async function VerifyReportPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  await requireRole(locale, ["reviewer"]);
  return <VerificationPage id={id} requestedLocale={locale} />;
}
