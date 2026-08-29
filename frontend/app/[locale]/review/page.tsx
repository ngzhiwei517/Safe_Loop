import { ReviewQueue } from "../../../components/reports/ReviewQueue";
import { requireRole } from "../../../lib/auth";

export default async function ReviewPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  await requireRole(locale, ["reviewer"]);
  return <ReviewQueue requestedLocale={locale} />;
}
