import { redirect } from "next/navigation";

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

export async function requireProfile(locale: string): Promise<{ role: AppRole }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect(`/${locale}/login`);

  const { data: profile } = await supabase
    .from("profiles")
    .select("role")
    .eq("id", user.id)
    .maybeSingle();
  if (!profile || !isAppRole(profile.role)) redirect(`/${locale}/not-authorised`);

  return { role: profile.role };
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
