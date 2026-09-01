import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const DEFAULT_CONFIG = Object.freeze({
  // Python interpreter that has pdf2zh installed. Override per-machine with
  // PDF2ZH_PYTHON (e.g. a conda env's python.exe). Default "python" uses PATH.
  python: "python",
  // Root of a pdf2zh checkout that contains tools/notes2viking.py. Override
  // with PDF2ZH_REPO. If empty, the plugin falls back to the working directory.
  repo: "",
  // OpenViking server base URL (for the ingest REST call).
  server: "http://127.0.0.1:1933",
  // Thread limit fix for the scipy-openblas "memory allocation failed" issue.
  openblasThreads: "1",
  // Default translation service: a provider name in providers.json, or a raw
  // "service:model" string (e.g. "google", "deepseek", "deepseek:deepseek-v4-flash").
  service: "google",
  // Default source/target language codes.
  langIn: "en",
  langOut: "zh",
  // JSON file mapping provider names -> {service, model, env}. API keys live
  // in each provider's `env` here. Default: <plugin dir>/providers.json.
  providersFile: "",
});

/** Load named providers from a JSON file: { name: {service, model, env} }. */
export function loadProviders(input = {}, env = process.env) {
  const file =
    input.providersFile ||
    env.PDF2ZH_PROVIDERS_FILE ||
    path.join(import.meta.dirname, "providers.json");
  if (!existsSync(file)) return {};
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return {};
  }
}

export function resolveConfig(input = {}, env = process.env) {
  const config = {
    ...DEFAULT_CONFIG,
    ...input,
    python: input.python || env.PDF2ZH_PYTHON || DEFAULT_CONFIG.python,
    repo: input.repo || env.PDF2ZH_REPO || DEFAULT_CONFIG.repo,
    server: input.server || env.PDF2ZH_SERVER || DEFAULT_CONFIG.server,
    openblasThreads:
      input.openblasThreads || env.PDF2ZH_OPENBLAS_THREADS || DEFAULT_CONFIG.openblasThreads,
    service: input.service || env.PDF2ZH_SERVICE || DEFAULT_CONFIG.service,
    langIn: input.langIn || env.PDF2ZH_LANG_IN || DEFAULT_CONFIG.langIn,
    langOut: input.langOut || env.PDF2ZH_LANG_OUT || DEFAULT_CONFIG.langOut,
  };
  config.providers = loadProviders(input, env);
  return config;
}
