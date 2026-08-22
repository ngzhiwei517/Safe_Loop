import { getTranslations } from "next-intl/server";

export default async function NotAuthorisedPage() {
  const t = await getTranslations();
  return <main className="mx-auto max-w-xl px-6 py-16"><h1 className="text-3xl font-bold">{t("app.notAuthorised.title")}</h1><p className="mt-4">{t("app.notAuthorised.detail")}</p></main>;
}
