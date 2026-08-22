import { SubmissionDone } from "../../../../components/reports/SubmissionDone";

export default async function ReportSubmittedPage({ params }: { params: Promise<{ locale: string; id: string }> }) {
  const { locale, id } = await params;
  return <SubmissionDone id={id} locale={locale} />;
}
