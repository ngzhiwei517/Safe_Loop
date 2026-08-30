"use client";

import { FormEvent, useState } from "react";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { EnvelopeIcon, LockClosedIcon } from "@heroicons/react/24/outline";
import { useLocale, useTranslations } from "next-intl";

import { createClient } from "../../lib/supabase/browser";
import {
  defaultLocale,
  isLocale,
  localeCookieName,
  locales,
  type Locale,
} from "../../lib/locales";
import safeLoopLogo from "./safeloop-logo.png";

export default function LoginForm() {
  const pathname = usePathname();
  const router = useRouter();
  const requestedLocale = useLocale();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const t = useTranslations();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function switchLocale(nextLocale: Locale) {
    if (nextLocale === locale) return;
    document.cookie = `${localeCookieName}=${encodeURIComponent(nextLocale)}; Path=/; Max-Age=31536000; SameSite=Lax`;
    const segments = pathname.split("/");
    segments[1] = nextLocale;
    router.replace(segments.join("/") || `/${nextLocale}/login`);
    router.refresh();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const { error: signInError } = await createClient().auth.signInWithPassword({ email, password });
    if (signInError) {
      setError(t("app.loginFailed"));
      return;
    }
    router.push(`/${locale}`);
    router.refresh();
  }

  return (
    <main className="min-h-screen bg-bg pb-12">
      <div className="hazard-stripe h-2 w-full" aria-hidden="true" />
      <div className="mx-auto flex w-full max-w-[520px] flex-col px-5 pb-10 pt-7 sm:px-7 sm:pt-10">
        <div
          className="ml-auto flex rounded-chip bg-surfaceSunken p-1"
          aria-label={t("app.language")}
        >
          {locales.toReversed().map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={option === locale}
              onClick={() => switchLocale(option)}
              className={`min-h-11 min-w-[88px] rounded-chip px-4 text-base font-bold transition-colors ${
                option === locale
                  ? "bg-surface text-ink shadow-safe"
                  : "text-inkMuted"
              }`}
            >
              {option === "en" ? t("app.languageEnglish") : t("login.languageChinese")}
            </button>
          ))}
        </div>

        <header className="mt-7 flex flex-col items-center text-center sm:mt-8">
          <div className="flex h-28 w-28 items-center justify-center overflow-hidden rounded-[32px] bg-surface p-2 shadow-safe">
            <Image
              src={safeLoopLogo}
              width={112}
              height={112}
              priority
              alt={t("login.logoAlt")}
              className="h-full w-full object-contain"
            />
          </div>
          <h1 className="mt-4 text-[2.4rem] font-bold leading-none tracking-tight">
            <span>{t("login.brandSafe")}</span><span className="text-primary">{t("login.brandLoop")}</span>
          </h1>
          <p className="mt-3 text-lg text-inkMuted">{t("login.tagline")}</p>
        </header>

        <section className="mt-8 rounded-[28px] border border-border bg-surface px-6 py-7 shadow-safe sm:px-7 sm:py-8">
          <h2 className="text-[1.75rem] font-bold leading-tight">{t("login.title")}</h2>
          <p className="mt-1 text-base text-inkMuted sm:text-lg">{t("login.subtitle")}</p>

          <form className="mt-7 space-y-6" onSubmit={submit}>
            <label className="block">
              <span className="text-sm font-bold uppercase tracking-wide">{t("app.email")}</span>
              <span className="mt-2 flex min-h-16 items-center gap-3 rounded-control border border-border bg-bg px-4 focus-within:border-primary focus-within:ring-2 focus-within:ring-primaryTint">
                <EnvelopeIcon className="h-6 w-6 shrink-0 text-inkMuted" aria-hidden="true" />
                <input
                  className="min-w-0 flex-1 bg-transparent text-lg text-ink outline-none placeholder:text-inkMuted"
                  type="email"
                  autoComplete="email"
                  placeholder={t("login.emailPlaceholder")}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </span>
            </label>

            <label className="block">
              <span className="text-sm font-bold uppercase tracking-wide">{t("app.password")}</span>
              <span className="mt-2 flex min-h-16 items-center gap-3 rounded-control border border-border bg-bg px-4 focus-within:border-primary focus-within:ring-2 focus-within:ring-primaryTint">
                <LockClosedIcon className="h-6 w-6 shrink-0 text-inkMuted" aria-hidden="true" />
                <input
                  className="min-w-0 flex-1 bg-transparent text-lg text-ink outline-none"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  type="button"
                  className="min-h-11 shrink-0 px-1 font-bold text-inkMuted"
                  aria-label={showPassword ? t("login.hidePassword") : t("login.showPassword")}
                  onClick={() => setShowPassword((current) => !current)}
                >
                  {showPassword ? t("login.hide") : t("login.show")}
                </button>
              </span>
            </label>

            {error && <p className="rounded-control bg-dangerTint p-3 font-bold text-danger" role="alert">{error}</p>}

            <button
              className="min-h-16 w-full rounded-control bg-primary px-4 text-xl font-bold text-ink-inverse shadow-safe transition-colors hover:bg-primaryStrong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              type="submit"
            >
              {t("app.signIn")}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
