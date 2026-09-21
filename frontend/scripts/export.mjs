import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const output = new URL("../out/", import.meta.url);
async function files(directory, prefix = "") {
  const entries = await readdir(directory, { withFileTypes: true });
  const paths = await Promise.all(
    entries.map((entry) =>
      entry.isDirectory()
        ? files(new URL(`${entry.name}/`, directory), `${prefix}${entry.name}/`)
        : [`${prefix}${entry.name}`],
    ),
  );
  return paths.flat();
}
const paths = (await files(output))
  .filter(
    (path) => path !== "sw.js" && !path.endsWith(".map") && path !== "404.html",
  )
  .sort();
const hash = createHash("sha256");
for (const path of paths) {
  hash.update(path);
  hash.update(await readFile(new URL(path, output)));
}
const manifest = paths.map(
  (path) => "/" + path.replace(/(^|\/)index\.html$/, "$1"),
);
const source = await readFile(
  new URL("../public/sw.js", import.meta.url),
  "utf8",
);
await writeFile(
  new URL("sw.js", output),
  source
    .replace("__CLIPO_BUILD__", hash.digest("hex").slice(0, 16))
    .replace("/* __CLIPO_PRECACHE__ */ []", JSON.stringify(manifest)),
);
const destination = new URL("../../backend/app/static/", import.meta.url);
await rm(destination, { recursive: true, force: true });
await mkdir(destination, { recursive: true });
await cp(output, destination, { recursive: true });
