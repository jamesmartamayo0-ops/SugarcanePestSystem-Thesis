import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

import { createElement, type ComponentType } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

/*
 * Node's type stripping cannot load JSX, so the skeleton module is compiled
 * with the project's TypeScript into node_modules/.cache (where "react"
 * still resolves) and rendered to static markup.
 */
const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "skeleton.tsx"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const outDir = join(here, "..", "node_modules", ".cache", "skeleton-test");
mkdirSync(outDir, { recursive: true });
const outFile = join(outDir, "skeleton.mjs");
writeFileSync(outFile, compiled);

type Props = Record<string, unknown>;
const skeleton = (await import(pathToFileURL(outFile).href)) as Record<
  string,
  ComponentType<Props>
>;

function render(name: string, props: Props = {}): string {
  const component = skeleton[name];
  assert.ok(component, `${name} is exported`);
  return renderToStaticMarkup(createElement(component, props));
}

/** Visible text inside the decorative (aria-hidden) body. */
function decorativeText(html: string): string {
  const start = html.indexOf('<div aria-hidden="true" class="gov-skeleton-body">');
  assert.notEqual(start, -1, "decorative body is aria-hidden");
  return html
    .slice(start)
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const READY_MADE: [string, Props, string][] = [
  [
    "TableSkeleton",
    { label: "Loading pest cases", columns: ["Case", "Status", "Actions"] },
    "Loading pest cases",
  ],
  ["DetailSkeleton", { label: "Loading inspection details", compare: true }, "Loading inspection details"],
  ["FormSkeleton", { label: "Loading farmers for the farm form" }, "Loading farmers for the farm form"],
  ["MonitoringMapSkeleton", {}, "Loading farm monitoring map"],
  ["MapCanvasLoading", { label: "Loading map", small: true }, "Loading map"],
  [
    "DashboardSummarySkeleton",
    { attentionCards: 4, pipelineGroups: [2, 2, 3, 2], progressRows: 3 },
    "Loading operational summary",
  ],
  ["ReportSkeleton", { statusRows: 9, tableColumns: ["Case", "Status", "Actions"] }, "Loading operational report"],
  ["CaseRecordSkeleton", {}, "Loading case record"],
  ["EvidencePhotosSkeleton", {}, "Loading evidence photos"],
];

for (const [name, props, label] of READY_MADE) {
  test(`${name} exposes one accessible loading status`, () => {
    const html = render(name, props);
    assert.match(html, /^<div role="status" aria-busy="true" aria-live="polite"/);
    assert.ok(html.includes(`<span class="sr-only">${label}</span>`), "screen-reader label");
    assert.equal(html.match(/role="status"/g)?.length, 1, "no nested status regions");
  });

  test(`${name} is decorative and not focusable`, () => {
    const html = render(name, props);
    assert.doesNotMatch(html, /<(a|button|input|select|textarea)\b/);
    assert.doesNotMatch(html, /tabindex=/i);
    assert.doesNotMatch(html, /href=/);
  });

  test(`${name} shows no placeholder data`, () => {
    const text = decorativeText(render(name, props));
    // Only static column headings may appear; never numbers or sample values.
    assert.doesNotMatch(text, /\d/);
    const headings = [
      ...((props.columns as string[] | undefined) ?? []),
      ...((props.tableColumns as string[] | undefined) ?? []),
    ];
    const leftover = headings.reduce((rest, heading) => rest.replace(heading, ""), text).trim();
    assert.equal(leftover, "", `unexpected text: ${leftover}`);
  });

  test(`${name} starts without the slow-loading notice`, () => {
    assert.doesNotMatch(render(name, props), /gov-skeleton-slow/);
  });
}

test("table skeleton keeps the real column count and requested rows", () => {
  const html = render("TableSkeleton", {
    label: "Loading farms",
    columns: ["Farm / plot", "Barangay", "Area (ha)", "Actions"],
    rows: 3,
    tableClassName: "min-w-[720px]",
  });
  assert.equal(html.match(/<th\b/g)?.length, 4);
  assert.equal(html.match(/<tr>/g)?.length, 4); // header + 3 rows
  assert.ok(html.includes('class="gov-table gov-skeleton-table min-w-[720px]"'));
});

test("dashboard skeleton mirrors the attention cards and pipeline groups", () => {
  const html = render("DashboardSummarySkeleton", {
    attentionCards: 4,
    pipelineGroups: [2, 2, 3, 2],
    progressRows: 3,
  });
  assert.equal(html.match(/gov-skeleton-attention-card/g)?.length, 4);
  assert.equal(html.match(/class="gov-pipeline-group"/g)?.length, 4);
});

test("slow-loading threshold is bounded", () => {
  const delay = (skeleton.SLOW_LOADING_MS as unknown as number);
  assert.ok(delay > 0 && delay <= 20_000);
});

test("stylesheet disables skeleton animation for reduced motion", () => {
  const css = readFileSync(join(here, "..", "app", "globals.css"), "utf8");
  assert.match(
    css,
    /@media \(prefers-reduced-motion: reduce\) \{\s*\.gov-skeleton \{\s*animation: none !important;/,
  );
});
