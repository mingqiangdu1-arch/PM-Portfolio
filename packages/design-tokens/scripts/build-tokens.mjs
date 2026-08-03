import { readFile, mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
export const sourcePath = resolve(scriptDirectory, "../../../Wireframe与UI设计/UI设计/design-tokens.json");
const outputDirectory = resolve(scriptDirectory, "../generated");

const toKebab = (value) => value.replace(/([a-z0-9])([A-Z])/g, "$1-$2").replace(/[^a-zA-Z0-9]+/g, "-").toLowerCase();

function getNode(document, dottedPath) {
  return dottedPath.split(".").reduce((node, key) => node?.[key], document);
}

function resolveValue(document, value) {
  if (typeof value === "string" && /^\{.+\}$/.test(value)) {
    const target = getNode(document, value.slice(1, -1));
    if (!target || !("$value" in target)) throw new Error(`Unknown token reference: ${value}`);
    return resolveValue(document, target.$value);
  }
  return value;
}

function formatValue(value) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (value && typeof value === "object" && "unit" in value) return `${value.value}${value.unit}`;
  if (value && typeof value === "object" && "offsetX" in value) {
    return `${value.offsetX}px ${value.offsetY}px ${value.blur}px ${value.spread}px ${value.color}`;
  }
  return null;
}

function collect(document, node = document, path = [], result = []) {
  if (node && typeof node === "object" && "$value" in node) {
    const resolved = resolveValue(document, node.$value);
    const formatted = formatValue(resolved);
    if (formatted) result.push({ name: path.map(toKebab).join("-"), value: formatted });
    if (resolved && typeof resolved === "object" && "fontFamily" in resolved) {
      const base = path.map(toKebab).join("-");
      result.push(
        { name: `font-family-${base}`, value: `"${resolved.fontFamily}"` },
        { name: `font-size-${base}`, value: `${resolved.fontSize}px` },
        { name: `font-weight-${base}`, value: String(resolved.fontWeight) },
        { name: `line-height-${base}`, value: `${resolved.lineHeight}px` },
      );
    }
    return result;
  }
  if (!node || typeof node !== "object" || Array.isArray(node)) return result;
  for (const [key, child] of Object.entries(node)) {
    if (!key.startsWith("$")) collect(document, child, [...path, key], result);
  }
  return result;
}

function assertReference(document, path, family) {
  const reference = getNode(document, path)?.$value;
  if (typeof reference !== "string" || !reference.startsWith(`{color.primitive.${family}.`)) {
    throw new Error(`${path} must reference the ${family} primitive family.`);
  }
}

export function validateSemanticRoles(document) {
  assertReference(document, "color.semantic.action.primary", "sage");
  assertReference(document, "color.semantic.action.primaryHover", "sage");
  assertReference(document, "color.semantic.bg.aiSubtle", "apricot");
  assertReference(document, "color.semantic.text.ai", "apricot");
  assertReference(document, "color.semantic.state.warningFg", "warning");
  assertReference(document, "color.semantic.state.errorFg", "error");
}

const tailwindTheme = `@theme inline {\n  --color-canvas: var(--color-semantic-bg-canvas);\n  --color-surface: var(--color-semantic-bg-surface);\n  --color-subtle: var(--color-semantic-bg-subtle);\n  --color-primary-subtle: var(--color-semantic-bg-primary-subtle);\n  --color-ai-subtle: var(--color-semantic-bg-ai-subtle);\n  --color-text-primary: var(--color-semantic-text-primary);\n  --color-secondary: var(--color-semantic-text-secondary);\n  --color-muted: var(--color-semantic-text-muted);\n  --color-inverse: var(--color-semantic-text-inverse);\n  --color-primary-action: var(--color-semantic-text-primary-action);\n  --color-ai: var(--color-semantic-text-ai);\n  --color-default: var(--color-semantic-border-default);\n  --color-focus: var(--color-semantic-border-focus);\n  --color-brand-primary: var(--color-semantic-action-primary);\n  --color-brand-primary-hover: var(--color-semantic-action-primary-hover);\n  --color-brand-primary-disabled: var(--color-semantic-action-primary-disabled);\n  --color-success: var(--color-semantic-state-success-fg);\n  --color-warning: var(--color-semantic-state-warning-fg);\n  --color-warning-subtle: var(--color-semantic-state-warning-bg);\n  --color-error: var(--color-semantic-state-error-fg);\n  --color-error-subtle: var(--color-semantic-state-error-bg);\n  --spacing-token-xs: var(--spacing-xs);\n  --spacing-token-sm: var(--spacing-sm);\n  --spacing-token-md: var(--spacing-md);\n  --spacing-token-lg: var(--spacing-lg);\n  --spacing-token-xl: var(--spacing-xl);\n  --spacing-token-2xl: var(--spacing-2xl);\n  --spacing-token-3xl: var(--spacing-3xl);\n  --spacing-control-md: var(--dimension-control-md);\n  --spacing-control-lg: var(--dimension-control-lg);\n  --radius-token-md: var(--radius-md);\n  --radius-token-lg: var(--radius-lg);\n  --container-content: var(--dimension-layout-content-max);\n}\n`;

export function buildArtifacts(document) {
  validateSemanticRoles(document);
  const declarations = collect(document).sort((a, b) => a.name.localeCompare(b.name));
  const css = `/* Generated from Wireframe与UI设计/UI设计/design-tokens.json. Do not edit. */\n:root {\n${declarations.map(({ name, value }) => `  --${name}: ${value};`).join("\n")}\n}\n`;
  return { css, tailwind: `/* Generated Tailwind semantic aliases. Do not edit. */\n${tailwindTheme}` };
}

async function main() {
  const document = JSON.parse(await readFile(sourcePath, "utf8"));
  const artifacts = buildArtifacts(document);
  await mkdir(outputDirectory, { recursive: true });
  await writeFile(resolve(outputDirectory, "tokens.css"), artifacts.css, "utf8");
  await writeFile(resolve(outputDirectory, "tailwind.css"), artifacts.tailwind, "utf8");
  console.log(`Generated ${collect(document).length} CSS token declarations.`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await main();
