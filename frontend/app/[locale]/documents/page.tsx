import { DocumentsPage } from "../../../components/documents/DocumentsPage";

export default async function CorpusPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <DocumentsPage requestedLocale={locale} />;
}
