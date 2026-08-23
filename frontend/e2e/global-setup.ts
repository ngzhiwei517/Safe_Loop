import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import type { FullConfig } from "@playwright/test";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { runtimePath, type E2ELocale, type E2ERuntime, type E2EUser } from "./runtime";

type FixtureRole = "reporter" | "reviewer" | "responsible";

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for the browser suite`);
  return value;
}

function assertLoopback(url: string): void {
  const hostname = new URL(url).hostname;
  if (!["127.0.0.1", "localhost", "::1", "[::1]"].includes(hostname)) {
    throw new Error("End-to-end tests may connect only to the local Supabase stack");
  }
}

function throwOnError(error: { message: string } | null, context: string): void {
  if (error) throw new Error(`${context}: ${error.message}`);
}

async function createFixtureUser(
  client: SupabaseClient,
  runId: string,
  password: string,
  key: string,
  role: FixtureRole,
  preferredLang: E2ELocale,
  displayName: string,
): Promise<E2EUser> {
  const email = `${runId}-${key}@safeloop.example`;
  const created = await client.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
    user_metadata: { full_name: displayName },
  });
  throwOnError(created.error, `create ${key} user`);
  if (!created.data.user) throw new Error(`create ${key} user returned no identity`);

  const updated = await client
    .from("profiles")
    .update({ role, preferred_lang: preferredLang, display_name: displayName })
    .eq("id", created.data.user.id);
  throwOnError(updated.error, `assign ${key} profile`);

  return {
    id: created.data.user.id,
    email,
    password,
    displayName,
  };
}

export default async function globalSetup(_config: FullConfig): Promise<void> {
  if (process.env.AI_PROVIDER !== "stub") {
    throw new Error("AI_PROVIDER must be stub for the browser suite");
  }
  const supabaseUrl = requiredEnvironment("NEXT_PUBLIC_SUPABASE_URL");
  const serviceRoleKey = requiredEnvironment("SUPABASE_SERVICE_ROLE_KEY");
  assertLoopback(supabaseUrl);

  const client = createClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const runId = `e2e-${randomUUID().slice(0, 12)}`;
  const password = `SafeLoop-${randomUUID()}-Aa1!`;
  const reporterEn = await createFixtureUser(
    client,
    runId,
    password,
    "reporter-en",
    "reporter",
    "en",
    "E2E Reporter",
  );
  const reporterZh = await createFixtureUser(
    client,
    runId,
    password,
    "reporter-zh",
    "reporter",
    "zh-CN",
    "测试报告人",
  );
  const reviewer = await createFixtureUser(
    client,
    runId,
    password,
    "reviewer",
    "reviewer",
    "en",
    "E2E Safety Reviewer",
  );
  const responsible = await createFixtureUser(
    client,
    runId,
    password,
    "responsible",
    "responsible",
    "en",
    "E2E Technician",
  );

  const manualReportResult = await client
    .from("reports")
    .insert({
      reporter_id: reporterEn.id,
      status: "ai_drafted",
      urgency: "medium",
      lang_original: "en",
      input_mode: "typed",
      description_original: `${runId} manual triage fixture`,
      location_text: "E2E Manual Triage Zone",
      activity: "Inspection",
      is_confidential: false,
    })
    .select("id,human_ref")
    .single();
  throwOnError(manualReportResult.error, "create manual-triage report");
  if (!manualReportResult.data) throw new Error("manual-triage report was not returned");
  const manualReport = manualReportResult.data as { id: string; human_ref: string };

  const invalidDraftResult = await client.from("ai_drafts").insert({
    report_id: manualReport.id,
    version: 1,
    provider: "stub",
    provider_ref: `${runId}-invalid-draft`,
    raw_json: { fixture: "manual_triage" },
    observed_facts: [],
    assumptions: [],
    missing_information: ["hazard_detail"],
    proposed_category: null,
    proposed_urgency: "medium",
    suggested_owner_role: "responsible",
    suggested_action: null,
    confidence: 0.2,
    needs_escalation: false,
    escalation_reason: null,
    citations: [],
    validation: "invalid",
    validation_errors: ["observed_facts_empty"],
    latency_ms: 0,
    tokens_in: 0,
    tokens_out: 0,
  });
  throwOnError(invalidDraftResult.error, "create invalid AI draft");

  const expiredReportResult = await client
    .from("reports")
    .insert({
      reporter_id: reporterZh.id,
      status: "lesson_published",
      urgency: "low",
      lang_original: "zh-CN",
      input_mode: "typed",
      description_original: `${runId} expired briefing fixture`,
      location_text: "E2E Expired Zone",
      activity: "Inspection",
      is_confidential: false,
    })
    .select("id")
    .single();
  throwOnError(expiredReportResult.error, "create expired-token report");
  if (!expiredReportResult.data) throw new Error("expired-token report was not returned");
  const expiredReport = expiredReportResult.data as { id: string };
  const expiredBriefingToken = `expired-${randomUUID().replaceAll("-", "")}`;
  const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const monthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
  const expiredBriefingResult = await client.from("briefings").insert({
    report_id: expiredReport.id,
    version: 1,
    body: {
      en: "This fixture must never render because its token is expired.",
      "zh-CN": "此测试简报已经失效，不应显示。",
    },
    status: "published",
    target_activity: "Inspection",
    target_location: "E2E Expired Zone",
    valid_from: monthAgo.toISOString(),
    valid_to: yesterday.toISOString(),
    qr_token: expiredBriefingToken,
    approved_by: reviewer.id,
    approved_at: monthAgo.toISOString(),
  });
  throwOnError(expiredBriefingResult.error, "create expired briefing");

  const runtime: E2ERuntime = {
    runId,
    users: { reporterEn, reporterZh, reviewer, responsible },
    manualTriage: {
      reportId: manualReport.id,
      humanRef: manualReport.human_ref,
    },
    expiredBriefingToken,
  };
  await mkdir(dirname(runtimePath), { recursive: true });
  await writeFile(runtimePath, `${JSON.stringify(runtime, null, 2)}\n`, "utf8");
}
