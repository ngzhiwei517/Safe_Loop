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

export function formatDate(value: Date | string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: siteTimeZone }).format(new Date(value));
}

export function formatNumber(value: number, locale: Locale): string { return new Intl.NumberFormat(locale).format(value); }

export function formatPercent(value: number, locale: Locale): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatDurationSeconds(value: number, locale: Locale): string {
  const [amount, unit]: [number, "second" | "minute" | "hour"] =
    value < 60
      ? [value, "second"]
      : value < 3600
        ? [value / 60, "minute"]
        : [value / 3600, "hour"];
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: 1,
  }).format(amount);
}

export function formatRelativeAge(
  value: Date | string,
  locale: Locale,
  now: Date = new Date(),
): string {
  const seconds = (new Date(value).getTime() - now.getTime()) / 1000;
  const absoluteSeconds = Math.abs(seconds);
  const [amount, unit]: [number, Intl.RelativeTimeFormatUnit] =
    absoluteSeconds < 60
      ? [seconds, "second"]
      : absoluteSeconds < 3600
        ? [seconds / 60, "minute"]
        : absoluteSeconds < 86400
          ? [seconds / 3600, "hour"]
          : [seconds / 86400, "day"];
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(Math.round(amount), unit);
}
