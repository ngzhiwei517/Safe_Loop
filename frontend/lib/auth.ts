import { redirect } from "next/navigation";

import { defaultLocale, isLocale, type Locale } from "./locales";
import { createClient } from "./supabase/server";

export type AppRole = "reporter" | "reviewer" | "responsible" | "crew" | "admin";

const appRoles = new Set<AppRole>([
  "reporter",
  "reviewer",
  "responsible",
  "crew",
  "admin",
]);

function isAppRole(value: unknown): value is AppRole {
  return typeof value === "string" && appRoles.has(value as AppRole);
}

export type CurrentProfile = {
  id: string;
  email: string | null;
  displayName: string;
  role: AppRole;
  preferredLanguage: Locale;
};

export async function requireCurrentProfile(
  locale: string,
): Promise<CurrentProfile> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect(`/${locale}/login`);

  const { data: profile } = await supabase
    .from("profiles")
    .select("id, role, preferred_lang, display_name")
    .eq("id", user.id)
    .maybeSingle();
  if (!profile || !isAppRole(profile.role)) redirect(`/${locale}/not-authorised`);

  const email = user.email ?? null;
  return {
    id: profile.id,
    email,
    displayName: profile.display_name?.trim()
      || user.user_metadata?.full_name
      || email?.split("@")[0]
      || `Site user ${user.id.slice(0, 8)}`,
    role: profile.role,
    preferredLanguage: isLocale(profile.preferred_lang)
      ? profile.preferred_lang
      : defaultLocale,
  };
}

export async function requireProfile(locale: string): Promise<{ role: AppRole }> {
  const { role } = await requireCurrentProfile(locale);
  return { role };
}

export async function requireRole<const Roles extends readonly AppRole[]>(
  locale: string,
  allowedRoles: Roles,
): Promise<{ role: Roles[number] }> {
  const profile = await requireProfile(locale);
  if (!(allowedRoles as readonly AppRole[]).includes(profile.role)) {
    redirect(`/${locale}/not-authorised`);
  }
  return profile as { role: Roles[number] };
}
