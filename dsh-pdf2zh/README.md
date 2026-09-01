# dsh-pdf2zh

DeepSeek Harness plugin exposing the **pdf2zh** pipeline — PDF translation →
structured per-paragraph notes → **OpenViking** ingestion — as native agent
tools:

| Tool | What it does |
|---|---|
| `pdf2zh_translate(pdf, service, lang_in, lang_out, output)` | Translate a PDF and export structured notes as JSONL (source + translation + headings + page markers + formulas). |
| `pdf2zh_ingest(jsonl, viking_uri)` | Ingest a `-notes.jsonl` into OpenViking (writes the resource, indexes it for semantic retrieval). |
| `pdf2viking(pdf, viking_uri, ...)` | One-shot: translate **and** ingest. |

The tools run on the **DSH host** (not the agent sandbox), so they have full
network / memory / filesystem access — this is what lets the heavy pdf2zh
pipeline (ONNX layout model, translation API, font downloads) run when invoked
by an agent.

> **Skeleton note**: the cordis registration and `defineTool` wrapper boilerplate
> are adapted from `@openviking/dsh-memory-plugin` (Apache-2.0). See `NOTICE`
> for attribution and the modified files.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| **DeepSeek Harness** (web profile) | Node >= 22 |
| **pdf2zh with the `--notes` feature** | See §1.1 — the official PyPI release does **not** have it |
| **OpenViking** server | Running at `http://127.0.0.1:1933` (default) |
| **A Python** that has that pdf2zh installed | Set in `~/.dsh/pdf2zh-config.json` (recommended) or `PDF2ZH_PYTHON` |

### 1.1 The pdf2zh dependency (important)

This plugin drives pdf2zh's `--notes --notes-format jsonl` pipeline, which is
**not yet in the official PyPI `pdf2zh` release** (it crashes on the unknown
`--notes` argument). Use the **maintainer's fork**, which includes it:

```powershell
pip install git+https://github.com/wqy-lab/PDFMathTranslate.git
```

**Alternative (no fork / no pip):** apply the bundled patch to a pdf2zh
**v1.9.11** checkout and point the plugin at it:

```powershell
.\setup-pdf2zh-notes.ps1 -Repo "<path-to-pdf2zh-checkout>"
```

---

## 2. Install

**From npm** (published):

```powershell
dsh plugin --profile web add dsh-pdf2zh
```

**From a local checkout** (development):

```powershell
dsh plugin --profile web add "file:///<absolute-path-to-this-directory>"
```

Either way, then add `"dsh-pdf2zh"` to `dsh.profile.bundles` in
`~/.dsh/profiles/web/package.json`, run `pnpm install` in that profile dir, and
**restart DSH**. The agent then has the three `pdf2zh_*` tools.

---

## 3. Configuration (detailed)

The plugin resolves settings from three layers (highest first):

```
tool call argument > env var > ~/.dsh config file > built-in default
```

### 3.1 Providers — translation services + API keys

`~/.dsh/pdf2zh-providers.json` maps a **name** → a pdf2zh service + model + API
env. Create it from the template shipped with the plugin:

```powershell
Copy-Item "<plugin dir>\providers.example.json" "$env:USERPROFILE\.dsh\pdf2zh-providers.json"
```

Fill in real keys:

```json
{
  "deepseek": {
    "service": "deepseek",
    "model": "deepseek-v4-flash",
    "env": {
      "DEEPSEEK_API_KEY": "sk-YOUR-KEY",
      "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1"
    }
  },
  "custom": {
    "service": "custom",
    "model": "your-model",
    "env": {
      "CUSTOM_API_KEY": "...",
      "CUSTOM_BASE_URL": "https://your-endpoint/v1"
    }
  },
  "google": { "service": "google", "model": "", "env": {} }
}
```

- `service` — a pdf2zh translator name (`google`, `deepseek`, `openai`,
  `custom`, …).
- `model` — the model to pass as `service:model` (empty if the service has none).
- `env` — env vars injected into the pdf2zh subprocess (API keys, base URLs).
  These **override** whatever the host environment provides.

Lookup order: `PDF2ZH_PROVIDERS_FILE` env → `~/.dsh/pdf2zh-providers.json` →
`<plugin dir>/providers.json` (dev).

> **Security**: this file contains plaintext API keys. Never commit it; the
> `providers.json` name is gitignored, and only the `providers.example.json`
> template is shipped.

### 3.2 Machine config — python / repo / defaults

`~/.dsh/pdf2zh-config.json` (optional, recommended) holds machine-specific
settings, read at plugin load — more reliable than env vars (no environment
propagation issues):

```json
{
  "python": "C:\\Users\\you\\.conda\\envs\\pdftranslate\\python.exe",
  "repo": "",
  "service": "deepseek",
  "langIn": "en",
  "langOut": "zh"
}
```

| Key | Meaning |
|---|---|
| `python` | Python that can run `-m pdf2zh.pdf2zh`. **Required** if pdf2zh isn't on PATH. |
| `repo` | pdf2zh checkout root. **Optional** — only needed for non-pip (patched-checkout) installs; the plugin bundles `notes2viking.py`, and pip-installed pdf2zh runs from any directory. |
| `service` | Default service (provider name or raw `service:model`). |
| `langIn` / `langOut` | Default source/target language codes. |
| `server` | OpenViking base URL (default `http://127.0.0.1:1933`). |

### 3.3 Env vars (alternative to the config file)

| Env var | Meaning |
|---|---|
| `PDF2ZH_PYTHON` | Python that has pdf2zh installed |
| `PDF2ZH_REPO` | pdf2zh checkout root (optional) |
| `PDF2ZH_SERVICE` | Default service |
| `PDF2ZH_LANG_IN` / `PDF2ZH_LANG_OUT` | Language codes |
| `PDF2ZH_SERVER` | OpenViking base URL |
| `PDF2ZH_PROVIDERS_FILE` | Custom providers.json location |
| `PDF2ZH_CONFIG_FILE` | Custom pdf2zh-config.json location |
| `PDF2ZH_OPENBLAS_THREADS` | Thread limit fix for scipy-openblas (default `1`) |

> Windows note: `setx` only affects new processes. If DSH was started before you
> set an env var, the host won't see it until restarted from a fresh terminal —
> another reason to prefer the config file (§3.2).

### 3.4 Verify

Restart DSH, then ask the agent: "list your pdf2zh tools". You should see the
three `pdf2zh_*` tools. Or run a tiny `pdf2zh_translate` on a small PDF and
confirm it produces a `-notes.jsonl`.

---

## 4. Usage

Give the agent a natural instruction; it calls the tools for you:

```text
「把 E:\papers\paper.pdf 翻译并入库到 viking:/resources/papers/<category>/<id>--<slug>.notes.md，用 deepseek」
```

The `service` argument accepts:
1. a **provider name** from `~/.dsh/pdf2zh-providers.json` (e.g. `deepseek`),
2. a raw **`service:model`** string (e.g. `deepseek:deepseek-v4-flash`),
3. nothing → the configured default.

Output artifacts (in the `output` dir, which is auto-created):
- `<name>-mono.pdf` / `<name>-dual.pdf` — translated PDFs
- `<name>-notes.jsonl` — structured per-paragraph notes (the RAG source)
- (after ingest) the resource is retrievable via OpenViking search.

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'cv2'` | The plugin ran a Python that lacks pdf2zh's deps. Set `python` in `~/.dsh/pdf2zh-config.json` to the env that has pdf2zh installed, restart DSH. |
| `OpenBLAS error: Memory allocation still failed` | scipy-openblas thread oversubscription. `PDF2ZH_OPENBLAS_THREADS=1` (default) fixes it. |
| `pdf2zh: error: unrecognized arguments: --notes` | Using the official PyPI pdf2zh. Install the fork (§1.1) or apply the patch. |
| `KeyError: 'DEEPSEEK_BASE_URL'` / `'OPENAI_API_KEY'` | A stale pdf2zh config cache. Remove `~/.cache/pdf2zh/` (or the stale translator config) and retry. |
| `401 / invalid API key` | `providers.json` still has placeholder keys; fill real ones. |
| Tool says `pdf2zh failed (exit 1)` with no detail | Check `PDF2ZH_PYTHON` resolves and that pdf2zh imports: `python -c "import pdf2zh"`. |

---

## 6. License

Apache-2.0. This plugin's bootstrap skeleton is derived from
`@openviking/dsh-memory-plugin` (Apache-2.0); see `NOTICE` for attribution and
the modified files. It **invokes** pdf2zh (AGPL-3.0) as an external process and
does not incorporate its code; install pdf2zh separately.
