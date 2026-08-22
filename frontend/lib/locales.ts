export const locales = ["en", "zh-CN"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";
export const localeCookieName = "safeloop-locale";
export const siteTimeZone = process.env.SITE_TIMEZONE ?? "Asia/Singapore";
export function isLocale(value: string): value is Locale { return (locales as readonly string[]).includes(value); }

export function localeFromAcceptLanguage(value: string | null): Locale {
  if (!value) return defaultLocale;
  const requested = value.split(",").map((entry) => entry.split(";")[0].trim());
  return locales.find((locale) => requested.some((tag) => tag.toLowerCase() === locale.toLowerCase() || tag.toLowerCase() === locale.split("-")[0].toLowerCase())) ?? defaultLocale;
}

export function formatDateTime(value: Date | string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: siteTimeZone }).format(new Date(value));
}

export function formatNumber(value: number, locale: Locale): string { return new Intl.NumberFormat(locale).format(value); }
