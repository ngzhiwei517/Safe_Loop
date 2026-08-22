import { redirect } from "next/navigation";

import { AlertsPage } from "../../../components/alerts/AlertsPage";
import { createClient } from "../../../lib/supabase/server";

export default async function AlertsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect(`/${locale}/login`);
  const { data: profile } = await supabase
    .from("profiles")
    .select("role")
    .eq("id", user.id)
    .single();
  if (profile?.role !== "reviewer" && profile?.role !== "admin") {
    redirect(`/${locale}/not-authorised`);
  }
  return <AlertsPage requestedLocale={locale} />;
}
