"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";

import { createClient } from "../../lib/supabase/browser";
import { defaultLocale, isLocale } from "../../lib/locales";

export default function LoginForm() {
  const router = useRouter();
  const requestedLocale = useLocale();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const t = useTranslations();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const { error: signInError } = await createClient().auth.signInWithPassword({ email, password });
    if (signInError) { setError(t("app.loginFailed")); return; }
    router.push(`/${locale}`);
    router.refresh();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-6">
      <h1 className="text-3xl font-bold">{t("app.name")}</h1>
      <form className="space-y-4" onSubmit={submit}>
        <label className="block">{t("app.email")}<input className="mt-1 w-full rounded-control border border-border bg-surface p-3" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label className="block">{t("app.password")}<input className="mt-1 w-full rounded-control border border-border bg-surface p-3" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        {error && <p role="alert">{error}</p>}
        <button className="min-h-14 w-full rounded-control bg-primary p-3 font-bold text-ink-inverse" type="submit">{t("app.signIn")}</button>
      </form>
    </main>
  );
}
