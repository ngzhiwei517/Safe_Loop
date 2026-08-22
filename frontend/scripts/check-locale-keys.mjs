import { readdir, readFile } from "node:fs/promises";

const files = (await readdir("messages")).filter((name) => name.endsWith(".json")).sort();
if (files.length !== 2) {
  console.error(`Expected two locale catalogues, found ${files.length}.`);
  process.exit(1);
}

const catalogues = await Promise.all(files.map(async (name) => ({ name, messages: JSON.parse(await readFile(`messages/${name}`, "utf8")) })));
const expected = Object.keys(catalogues[0].messages).sort();
const failures = catalogues.flatMap(({ name, messages }) => {
  const actual = Object.keys(messages).sort();
  return expected.filter((key) => !actual.includes(key)).map((key) => `${name} missing ${key}`)
    .concat(actual.filter((key) => !expected.includes(key)).map((key) => `${catalogues[0].name} missing ${key}`));
});

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("Locale keys match.");
