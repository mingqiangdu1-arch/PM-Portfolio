import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const schemaPath = process.env.OPENAPI_SCHEMA_PATH;
if (!schemaPath || !existsSync(schemaPath)) {
  console.error("api:generate requires OPENAPI_SCHEMA_PATH pointing to the Review-frozen OpenAPI JSON.");
  process.exit(1);
}

const expectedHash = "c37c50a3bebfe77daa245363dac9dae2212f303f59deff823540bddc2b7a6039";
const actualHash = createHash("sha256").update(readFileSync(schemaPath)).digest("hex");
if (actualHash !== expectedHash) {
  console.error(`OpenAPI contract hash mismatch: expected ${expectedHash}, got ${actualHash}`);
  process.exit(1);
}

const orvalBin = resolve(import.meta.dirname, "..", "node_modules", "orval", "dist", "bin", "orval.mjs");
const result = spawnSync(process.execPath, [orvalBin, "--config", "orval.config.mjs"], {
  cwd: resolve(import.meta.dirname, ".."),
  stdio: "inherit",
  env: { ...process.env, OPENAPI_SCHEMA_PATH: resolve(schemaPath) },
});
if (result.error) throw result.error;
if (result.status === 0) {
  const clientPath = resolve(import.meta.dirname, "..", "src", "lib", "api", "generated", "client.ts");
  writeFileSync(clientPath, readFileSync(clientPath, "utf8").replace(/\r?\n(?:\r?\n)+$/u, "\n"));
}
process.exit(result.status ?? 1);
