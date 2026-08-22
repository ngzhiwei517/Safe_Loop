import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { defaultLocale, isLocale, localeCookieName, localeFromAcceptLanguage, type Locale } from "./lib/locales";

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );

  const firstSegment = request.nextUrl.pathname.split("/")[1];
  if (isLocale(firstSegment)) {
    await supabase.auth.getUser();
    return response;
  }

  let locale: Locale | undefined;
  const { data: { user } } = await supabase.auth.getUser();
  if (user) {
    const { data: profile } = await supabase.from("profiles").select("preferred_lang").eq("id", user.id).maybeSingle();
    if (profile && isLocale(profile.preferred_lang)) locale = profile.preferred_lang;
  }
  const cookieLocale = request.cookies.get(localeCookieName)?.value;
  if (!locale && cookieLocale && isLocale(cookieLocale)) locale = cookieLocale;
  locale ??= localeFromAcceptLanguage(request.headers.get("accept-language"));
  locale ??= defaultLocale;

  const url = request.nextUrl.clone();
  url.pathname = `/${locale}${request.nextUrl.pathname}`;
  const redirectResponse = NextResponse.redirect(url);
  response.cookies.getAll().forEach((cookie) => redirectResponse.cookies.set(cookie));
  return redirectResponse;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|api).*)"] };
