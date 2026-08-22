import { getTranslations } from "next-intl/server";

export default async function NewReportPage() {
  const t = await getTranslations();
  return <main className="mx-auto max-w-xl px-6 py-16"><h1 className="text-3xl font-bold">{t("report.new.title")}</h1><p className="mt-4">{t("report.new.placeholder")}</p></main>;
}
