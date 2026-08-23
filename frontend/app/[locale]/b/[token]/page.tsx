import { CrewBriefingPage } from "../../../../components/learning/CrewBriefingPage";
import { ApiError } from "../../../../lib/api";
import { getPublicBriefing, type PublicBriefing } from "../../../../lib/briefings";

export const dynamic = "force-dynamic";

export default async function PublicBriefingRoute({
  params,
}: {
  params: Promise<{ locale: string; token: string }>;
}) {
  const { locale, token } = await params;
  let briefing: PublicBriefing | null = null;
  let loadUnavailable = false;
  try {
    briefing = await getPublicBriefing(token);
  } catch (error) {
    briefing = null;
    loadUnavailable = !(
      error instanceof ApiError
      && error.body.detail.code === "briefing_inactive"
    );
  }
  return (
    <CrewBriefingPage
      requestedLocale={locale}
      token={token}
      briefing={briefing}
      loadUnavailable={loadUnavailable}
    />
  );
}
