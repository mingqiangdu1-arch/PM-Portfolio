import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { buildArtifacts, sourcePath, validateSemanticRoles } from "../scripts/build-tokens.mjs";

describe("design token build", () => {
  it("preserves Sage, Apricot, Amber and Red semantic roles", async () => {
    const document = JSON.parse(await readFile(sourcePath, "utf8"));
    expect(() => validateSemanticRoles(document)).not.toThrow();
  });

  it("matches the generated CSS snapshot", async () => {
    const document = JSON.parse(await readFile(sourcePath, "utf8"));
    expect(buildArtifacts(document)).toMatchSnapshot();
  });
});
