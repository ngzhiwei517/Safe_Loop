import { redirect } from "next/navigation";

import { createClient } from "../../lib/supabase/server";

export default async function LocaleHome({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect(`/${locale}/login`);
  const { data: profile } = await supabase.from("profiles").select("role").eq("id", user.id).single();
  if (profile?.role === "reporter") redirect(`/${locale}/report/new`);
  if (profile?.role === "reviewer") redirect(`/${locale}/review`);
  redirect(`/${locale}/not-authorised`);
}
