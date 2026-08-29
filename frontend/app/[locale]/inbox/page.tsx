import { InboxPage } from "../../../components/notifications/InboxPage";
import { requireProfile } from "../../../lib/auth";

export default async function InboxRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const { role } = await requireProfile(locale);
  return <InboxPage requestedLocale={locale} role={role} />;
}
