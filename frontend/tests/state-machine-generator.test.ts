import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { promisify } from "node:util";

import { afterEach, describe, expect, it } from "vitest";

const execute = promisify(execFile);
const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) =>
      rm(directory, { recursive: true, force: true }),
    ),
  );
});

describe("state-machine generation", () => {
  it("is explicit and does not make production builds depend on a running API", async () => {
    const packageJson = JSON.parse(
      await readFile(resolve(process.cwd(), "package.json"), "utf8"),
    ) as { scripts: Record<string, string> };

    expect(packageJson.scripts["generate-state-machine"]).toBe(
      "node scripts/generate-state-machine.mjs",
    );
    expect(packageJson.scripts.build).not.toContain("generate-state-machine");
  });

  it("fails without replacing the last valid contract when the API is unavailable", async () => {
    const directory = await mkdtemp(resolve(tmpdir(), "safeloop-state-machine-"));
    temporaryDirectories.push(directory);
    await mkdir(resolve(directory, "lib"));
    const generatedPath = resolve(directory, "lib", "stateMachine.ts");
    await writeFile(generatedPath, "last-valid-contract", "utf8");

    await expect(
      execute(
        process.execPath,
        [resolve(process.cwd(), "scripts", "generate-state-machine.mjs")],
        {
          cwd: directory,
          env: {
            ...process.env,
            STATE_MACHINE_URL: "invalid://state-machine",
          },
        },
      ),
    ).rejects.toThrow();
    await expect(readFile(generatedPath, "utf8")).resolves.toBe(
      "last-valid-contract",
    );
  });
});
