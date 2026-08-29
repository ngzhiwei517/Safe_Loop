import { DocumentsPage } from "../../../components/documents/DocumentsPage";
import { requireRole } from "../../../lib/auth";

export default async function CorpusPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const { role } = await requireRole(locale, ["reviewer", "admin"]);
  return <DocumentsPage requestedLocale={locale} role={role} />;
}
