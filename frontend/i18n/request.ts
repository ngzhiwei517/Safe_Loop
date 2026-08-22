import { getRequestConfig } from "next-intl/server";
import { defaultLocale, isLocale } from "../lib/locales";

interface Messages { [key: string]: string | Messages }

function expandMessages(flat: Record<string, string>): Messages {
  const expanded: Messages = {};
  for (const [key, value] of Object.entries(flat)) {
    const parts = key.split(".");
    let cursor = expanded;
    for (const part of parts.slice(0, -1)) {
      const next = cursor[part];
      if (!next || typeof next === "string") cursor[part] = {};
      cursor = cursor[part] as Messages;
    }
    cursor[parts.at(-1)!] = value;
  }
  return expanded;
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = requested && isLocale(requested) ? requested : defaultLocale;
  const flat = (await import(`../messages/${locale}.json`)).default as Record<string, string>;
  return { locale, messages: expandMessages(flat) };
});
