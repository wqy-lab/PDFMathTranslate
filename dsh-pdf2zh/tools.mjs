import path from "node:path";
import { existsSync, mkdirSync } from "node:fs";
import { defineTool } from "@deepseek-ai/dsh-tools";
import { runCommand, stripAnsi } from "./runner.mjs";

function textTool(definition) {
  return defineTool({
    ...definition,
    output: {
      schema: { type: "string" },
      render: (_args, value) => [{ type: "text", text: value }],
    },
    presentCall: (args) => ({
      card: "generic",
      kind: "tool",
      title: definition.name,
      rawInput: args,
    }),
  });
}

/**
 * Resolve a service spec: a provider NAME in config.providers (mapped to
 * {service, model, env}), or a raw "service:model" string used as-is.
 */
function resolveService(config, svc) {
  const provider = config.providers && config.providers[svc];
  if (!provider) return { arg: svc, env: {} };
  const modelSuffix = provider.model ? `:${provider.model}` : "";
  return { arg: `${provider.service}${modelSuffix}`, env: provider.env || {} };
}

/** Repo root: explicit config, or fall back to the working directory. */
function repoRoot(config) {
  return config.repo || process.cwd();
}

/** Run `python -m pdf2zh.pdf2zh` to translate + export notes JSONL. */
async function doTranslate(config, { pdf, service, lang_in, lang_out, output }) {
  const svc = service || config.service;
  const { arg: svcArg, env: providerEnv } = resolveService(config, svc);
  const li = lang_in || config.langIn;
  const lo = lang_out || config.langOut;
  const outDir = output || path.dirname(path.resolve(pdf));
  const stem = path.basename(pdf, path.extname(pdf));
  const jsonl = path.join(outDir, `${stem}-notes.jsonl`);
  if (outDir) mkdirSync(outDir, { recursive: true });

  const r = await runCommand(
    config.python,
    [
      "-m", "pdf2zh.pdf2zh",
      pdf,
      "--notes", "--notes-format", "jsonl",
      "-s", svcArg,
      "-li", li,
      "-lo", lo,
      "-o", outDir,
    ],
    {
      cwd: repoRoot(config),
      env: { ...providerEnv, OPENBLAS_NUM_THREADS: config.openblasThreads },
    },
  );

  if (r.code !== 0) {
    return { ok: false, message: `pdf2zh failed (exit ${r.code}):\n${stripAnsi(r.stderr || r.stdout)}` };
  }
  return {
    ok: true,
    jsonl,
    message: `Translation done.\nnotes.jsonl: ${jsonl}\n${tailLines(stripAnsi(r.stdout), 6)}`,
  };
}

/** Ingest a -notes.jsonl into OpenViking via notes2viking.py --run. */
async function doIngest(config, { jsonl, viking_uri }) {
  // Prefer the bundled copy shipped with the plugin; fall back to a repo copy.
  const bundled = path.join(import.meta.dirname, "notes2viking.py");
  const script = existsSync(bundled)
    ? bundled
    : path.join(repoRoot(config), "tools", "notes2viking.py");
  const r = await runCommand(
    config.python,
    [script, jsonl, "--to", viking_uri, "--run", "--server", config.server],
  );
  if (r.code !== 0) {
    return { ok: false, message: `ingest failed (exit ${r.code}):\n${stripAnsi(r.stderr || r.stdout)}` };
  }
  return { ok: true, message: stripAnsi(r.stdout).trim() };
}

function tailLines(text, n) {
  const lines = String(text).split(/\r?\n/).filter(Boolean);
  return lines.slice(-n).join("\n");
}

export function registerPdf2zhTools(ctx, config) {
  ctx.tools.register(textTool({
    name: "pdf2zh_translate",
    description:
      "Translate a PDF/Word file and export structured per-paragraph notes (source + translation + headings + page markers + formulas) as JSONL, ready for RAG/OpenViking. Returns the notes.jsonl path.",
    parameters: {
      pdf: { type: "string", required: true, description: "Absolute path to the PDF (or .doc/.docx)." },
      service: { type: "string", description: "Provider name from providers.json (e.g. deepseek, google) or a raw service:model string. Default: config.service." },
      lang_in: { type: "string", description: "Source language code (default en)." },
      lang_out: { type: "string", description: "Target language code (default zh)." },
      output: { type: "string", description: "Output directory (default: the PDF's directory)." },
    },
    async execute(args) {
      const res = await doTranslate(config, args);
      return res.message;
    },
  }));

  ctx.tools.register(textTool({
    name: "pdf2zh_ingest",
    description:
      "Ingest a pdf2zh -notes.jsonl into OpenViking via the REST API (writes the resource and indexes it for viking_search). Returns the ingest status.",
    parameters: {
      jsonl: { type: "string", required: true, description: "Path to the -notes.jsonl produced by pdf2zh_translate." },
      viking_uri: { type: "string", required: true, description: "Target viking URI, e.g. viking:/<namespace>/<category>/<id>--<slug>.notes.md" },
    },
    async execute(args) {
      const res = await doIngest(config, args);
      return res.message;
    },
  }));

  ctx.tools.register(textTool({
    name: "pdf2viking",
    description:
      "One-shot pipeline: translate a PDF into structured notes, then ingest them into OpenViking. Returns the notes.jsonl path and the viking URI.",
    parameters: {
      pdf: { type: "string", required: true, description: "Absolute path to the PDF." },
      viking_uri: { type: "string", required: true, description: "Target viking URI for the notes resource." },
      service: { type: "string", description: "Provider name from providers.json, or raw service:model (default: config.service)." },
      lang_in: { type: "string", description: "Source language (default en)." },
      lang_out: { type: "string", description: "Target language (default zh)." },
      output: { type: "string", description: "Output directory (default: the PDF's directory)." },
    },
    async execute(args) {
      const tr = await doTranslate(config, args);
      if (!tr.ok) return tr.message;
      const ing = await doIngest(config, { jsonl: tr.jsonl, viking_uri: args.viking_uri });
      return `${tr.message}\n\n${ing.ok ? "Ingested:" : ""}\n${ing.message}`;
    },
  }));
}
