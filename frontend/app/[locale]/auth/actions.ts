"use server";

import { redirect } from "next/navigation";

import { defaultLocale, isLocale } from "../../../lib/locales";
import { createClient } from "../../../lib/supabase/server";

export async function signOut(requestedLocale: string): Promise<never> {
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const supabase = await createClient();
  const { error } = await supabase.auth.signOut();
  if (error) throw new Error("sign_out_failed");
  redirect(`/${locale}/login`);
}
