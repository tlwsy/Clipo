import { readFileSync, readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = fileURLToPath(new URL("../", import.meta.url));
function check(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) check(file);
    else if (file.endsWith(".mjs")) {
      const result = spawnSync(process.execPath, ["--check", file], {
        stdio: "inherit",
      });
      if (result.status) process.exit(result.status);
    }
  }
}
check(root);
const manifest = JSON.parse(readFileSync(path.join(root, "manifest.json")));
if (
  manifest.host_permissions ||
  manifest.content_scripts ||
  JSON.stringify([...manifest.permissions].sort()) !==
    JSON.stringify(["activeTab", "contextMenus", "scripting", "storage"])
)
  throw new Error("Unexpected install permissions");
for (const file of [
  manifest.background.service_worker,
  manifest.action.default_popup,
  manifest.options_page,
  ...Object.values(manifest.icons),
])
  readFileSync(path.join(root, file));
console.log("扩展脚本语法、入口文件与安装权限检查通过");
