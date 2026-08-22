import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  env: { SITE_TIMEZONE: process.env.SITE_TIMEZONE ?? "Asia/Singapore" },
};

export default withNextIntl(nextConfig);
