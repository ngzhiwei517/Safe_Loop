import { VerificationPage } from "../../../../components/reports/VerificationPage";

export default async function VerifyReportPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <VerificationPage id={id} requestedLocale={locale} />;
}
