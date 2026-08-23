import { redirect } from "next/navigation";

import { LearnPage } from "../../../components/learning/LearnPage";
import { createClient } from "../../../lib/supabase/server";

type AppRole = "reporter" | "reviewer" | "responsible" | "crew" | "admin";

export default async function LearnRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect(`/${locale}/login`);
  const { data: profile } = await supabase
    .from("profiles")
    .select("role")
    .eq("id", user.id)
    .single();
  if (!profile) redirect(`/${locale}/not-authorised`);
  return <LearnPage requestedLocale={locale} role={profile.role as AppRole} />;
}
