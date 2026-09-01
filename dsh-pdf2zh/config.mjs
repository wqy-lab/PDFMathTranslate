import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
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
  // in each provider's `env` here. Default: ~/.dsh/pdf2zh-providers.json
  // (stable, survives plugin upgrades); falls back to <plugin dir>/providers.json.
  providersFile: "",
});

/** Load named providers from a JSON file: { name: {service, model, env} }. */
export function loadProviders(input = {}, env = process.env) {
  const explicit = input.providersFile || env.PDF2ZH_PROVIDERS_FILE;
  const homeFile = path.join(homedir(), ".dsh", "pdf2zh-providers.json");
  const devFile = path.join(import.meta.dirname, "providers.json");
  // Explicit env/config wins; else ~/.dsh (stable); else plugin dir (dev).
  const file = explicit || (existsSync(homeFile) ? homeFile : devFile);
  if (!existsSync(file)) return {};
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return {};
  }
}

/**
 * Optional machine-level config file at ~/.dsh/pdf2zh-config.json, e.g.
 * {"python": "C:\\...\\python.exe", "repo": "C:\\...", "service": "deepseek"}.
 * Read at plugin load; more reliable than env vars (no env-propagation issues).
 */
export function loadConfigFile(input = {}, env = process.env) {
  const file =
    input.configFile || env.PDF2ZH_CONFIG_FILE ||
    path.join(homedir(), ".dsh", "pdf2zh-config.json");
  if (!existsSync(file)) return {};
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return {};
  }
}

export function resolveConfig(input = {}, env = process.env) {
  const fileCfg = loadConfigFile(input, env);
  // Precedence: input (cordis) > env vars > config file > defaults.
  const pick = (key, envName) => {
    const keys = ["python", "repo", "server", "openblasThreads", "service", "langIn", "langOut"];
    if (!keys.includes(key)) return undefined;
    return (
      input[key] ??
      env[envName] ??
      fileCfg[key] ??
      DEFAULT_CONFIG[key]
    );
  };
  const config = {
    ...DEFAULT_CONFIG,
    ...fileCfg,
    ...input,
    python: pick("python", "PDF2ZH_PYTHON"),
    repo: pick("repo", "PDF2ZH_REPO"),
    server: pick("server", "PDF2ZH_SERVER"),
    openblasThreads: pick("openblasThreads", "PDF2ZH_OPENBLAS_THREADS"),
    service: pick("service", "PDF2ZH_SERVICE"),
    langIn: pick("langIn", "PDF2ZH_LANG_IN"),
    langOut: pick("langOut", "PDF2ZH_LANG_OUT"),
  };
  config.providers = loadProviders(input, env);
  return config;
}
