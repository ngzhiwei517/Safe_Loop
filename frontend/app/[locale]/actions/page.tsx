import { ActionsPage } from "../../../components/actions/ActionsPage";

export default async function ActionsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <ActionsPage requestedLocale={locale} />;
}
