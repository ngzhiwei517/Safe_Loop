import { rm } from "node:fs/promises";

import type { FullConfig } from "@playwright/test";
import { createClient } from "@supabase/supabase-js";

import { readRuntime, runtimePath, type E2ERuntime } from "./runtime";

function throwOnError(error: { message: string } | null, context: string): void {
  if (error) throw new Error(`${context}: ${error.message}`);
}

export default async function globalTeardown(_config: FullConfig): Promise<void> {
  if (process.env.E2E_KEEP_DATA === "1") return;
  let runtime: E2ERuntime;
  try {
    runtime = readRuntime();
  } catch {
    return;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceRoleKey) return;
  const hostname = new URL(supabaseUrl).hostname;
  if (!["127.0.0.1", "localhost", "::1", "[::1]"].includes(hostname)) {
    throw new Error("End-to-end cleanup refused a non-local Supabase URL");
  }

  const client = createClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const userIds = Object.values(runtime.users).map((user) => user.id);
  const reporterIds = [runtime.users.reporterEn.id, runtime.users.reporterZh.id];

  const reports = await client.from("reports").delete().in("reporter_id", reporterIds);
  throwOnError(reports.error, "delete E2E reports");
  const notifications = await client
    .from("notifications")
    .delete()
    .in("recipient_id", userIds);
  throwOnError(notifications.error, "delete E2E notifications");
  const profiles = await client.from("profiles").delete().in("id", userIds);
  throwOnError(profiles.error, "delete E2E profiles");
  for (const userId of userIds) {
    const deleted = await client.auth.admin.deleteUser(userId);
    throwOnError(deleted.error, "delete E2E Auth user");
  }
  await rm(runtimePath, { force: true });
}
