import { ProfilePage } from "../../../components/profile/ProfilePage";
import { requireCurrentProfile } from "../../../lib/auth";

export default async function ProfileRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const profile = await requireCurrentProfile(locale);
  return <ProfilePage requestedLocale={locale} profile={profile} />;
}
