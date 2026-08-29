"use client";

import { ArrowRightStartOnRectangleIcon } from "@heroicons/react/24/outline";
import { useLocale, useTranslations } from "next-intl";
import { useFormStatus } from "react-dom";

import { signOut } from "../../app/[locale]/auth/actions";
import { defaultLocale, isLocale } from "../../lib/locales";

function SubmitButton({
  label,
  pendingLabel,
  variant,
}: {
  label: string;
  pendingLabel: string;
  variant: "nav" | "icon" | "text";
}) {
  const { pending } = useFormStatus();
  const accessibleLabel = pending ? pendingLabel : label;

  if (variant === "icon") {
    return (
      <button
        aria-label={accessibleLabel}
        className="grid min-h-11 min-w-11 place-items-center rounded-control border border-border bg-surface text-inkMuted disabled:opacity-60"
        disabled={pending}
        title={accessibleLabel}
        type="submit"
      >
        <ArrowRightStartOnRectangleIcon className="h-6 w-6" />
      </button>
    );
  }

  if (variant === "text") {
    return (
      <button
        className="min-h-11 rounded-control border border-border bg-surface px-4 text-sm font-bold text-ink disabled:opacity-60"
        disabled={pending}
        type="submit"
      >
        {accessibleLabel}
      </button>
    );
  }

  return (
    <button
      className="flex min-h-11 w-full flex-col items-center justify-center gap-1 text-xs font-bold text-inkMuted disabled:opacity-60"
      disabled={pending}
      type="submit"
    >
      <ArrowRightStartOnRectangleIcon className="h-5 w-5" />
      <span>{accessibleLabel}</span>
    </button>
  );
}

export function SignOutButton({
  variant = "nav",
}: {
  variant?: "nav" | "icon" | "text";
}) {
  const requestedLocale = useLocale();
  const locale = isLocale(requestedLocale) ? requestedLocale : defaultLocale;
  const t = useTranslations();
  const action = signOut.bind(null, locale);

  return (
    <form action={action} className={variant === "nav" ? "flex-1" : undefined}>
      <SubmitButton
        label={t("app.signOut")}
        pendingLabel={t("app.signingOut")}
        variant={variant}
      />
    </form>
  );
}
