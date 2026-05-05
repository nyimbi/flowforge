/**
 * gen.ts — Generate TypeScript types from the flowforge JSON schemas.
 * Run: pnpm gen
 */
import { compile } from "json-schema-to-typescript";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const schemaDir = resolve(
  __dirname,
  "../../../python/flowforge-core/src/flowforge/dsl/schema"
);
const outDir = resolve(__dirname, "../src");

mkdirSync(outDir, { recursive: true });

interface SchemaTarget {
  schemaFile: string;
  outFile: string;
  bannerComment: string;
}

const targets: SchemaTarget[] = [
  {
    schemaFile: "workflow_def.schema.json",
    outFile: "workflow_def.ts",
    bannerComment:
      "// Generated from workflow_def.schema.json — do not edit by hand.\n// Run `pnpm gen` to regenerate.",
  },
  {
    schemaFile: "form_spec.schema.json",
    outFile: "form_spec.ts",
    bannerComment:
      "// Generated from form_spec.schema.json — do not edit by hand.\n// Run `pnpm gen` to regenerate.",
  },
  {
    schemaFile: "jtbd-1.0.schema.json",
    outFile: "jtbd.ts",
    bannerComment:
      "// Generated from jtbd-1.0.schema.json — do not edit by hand.\n// Run `pnpm gen` to regenerate.",
  },
];

for (const { schemaFile, outFile, bannerComment } of targets) {
  const schemaPath = resolve(schemaDir, schemaFile);
  const schema = JSON.parse(readFileSync(schemaPath, "utf-8"));

  const ts = await compile(schema, schema.title ?? outFile, {
    bannerComment,
    additionalProperties: false,
    unknownAny: true,
    enableConstEnums: true,
    strictIndexSignatures: false,
    style: {
      singleQuote: false,
      semi: true,
    },
  });

  const outPath = resolve(outDir, outFile);
  writeFileSync(outPath, ts);
  console.log(`Generated ${outFile}`);
}

console.log("Type generation complete.");
