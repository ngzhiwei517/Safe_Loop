import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export type E2ELocale = "en" | "zh-CN";

export type E2EUser = {
  id: string;
  email: string;
  password: string;
  displayName: string;
};

export type E2ERuntime = {
  runId: string;
  users: {
    reporterEn: E2EUser;
    reporterZh: E2EUser;
    reviewer: E2EUser;
    responsible: E2EUser;
  };
  manualTriage: {
    reportId: string;
    humanRef: string;
  };
  expiredBriefingToken: string;
};

export const runtimePath = resolve(process.cwd(), "e2e", ".runtime.json");

export function readRuntime(): E2ERuntime {
  return JSON.parse(readFileSync(runtimePath, "utf8")) as E2ERuntime;
}
