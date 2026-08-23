"use client";

import { usePathname, useRouter } from "next/navigation";

import { localeCookieName, type Locale } from "../../lib/locales";
import { createClient } from "../../lib/supabase/browser";

type Option = { value: Locale; label: string };

export function LanguageSwitch({ current, options, label, onChange, persistProfile = true }: { current: Locale; options: Option[]; label: string; onChange?: (value: Locale) => void; persistProfile?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();

  async function switchLocale(nextLocale: Locale) {
    document.cookie = `${localeCookieName}=${encodeURIComponent(nextLocale)}; Path=/; Max-Age=31536000; SameSite=Lax`;
    if (persistProfile) {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (user) await supabase.from("profiles").update({ preferred_lang: nextLocale }).eq("id", user.id);
    }
    onChange?.(nextLocale);
    const segments = pathname.split("/");
    segments[1] = nextLocale;
    router.replace(segments.join("/") || `/${nextLocale}`);
    router.refresh();
  }

  return <div className="flex gap-2" aria-label={label}>{options.map((option) => <button type="button" key={option.value} onClick={() => void switchLocale(option.value)} className={`min-h-11 rounded-chip px-3 text-sm font-bold ${option.value === current ? "bg-ink text-ink-inverse" : "border border-border bg-surface text-inkMuted"}`}>{option.label}</button>)}</div>;
}
