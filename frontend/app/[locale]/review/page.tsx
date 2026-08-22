import { ReviewQueue } from "../../../components/reports/ReviewQueue";

export default async function ReviewPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <ReviewQueue requestedLocale={locale} />;
}
