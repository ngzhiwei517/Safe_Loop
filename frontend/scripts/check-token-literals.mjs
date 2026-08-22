import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const roots = ["app", "components", "lib"];
const hex = /#[0-9a-f]{3,8}\b/gi;
const violations = [];

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await walk(path);
    else if (/\.(css|ts|tsx|js|mjs)$/.test(entry.name)) {
      const matches = (await readFile(path, "utf8")).match(hex);
      if (matches && path.replaceAll("\\\\", "/") !== "app/globals.css") violations.push(`${path}: ${matches.join(", ")}`);
    }
  }
}

for (const root of roots) await walk(root);
if (violations.length) {
  console.error("Hex literals must live in app/globals.css:");
  console.error(violations.join("\n"));
  process.exit(1);
}
