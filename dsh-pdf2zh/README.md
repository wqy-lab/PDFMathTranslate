# dsh-pdf2zh

DeepSeek Harness plugin exposing the pdf2zh pipeline (PDF translation → structured
notes → OpenViking ingestion) as native agent tools:

- `pdf2zh_translate(pdf, service, lang_in, lang_out, output)` — translate a PDF and
  export structured per-paragraph notes JSONL.
- `pdf2zh_ingest(jsonl, viking_uri)` — ingest the JSONL into OpenViking (indexed,
  retrievable via OpenViking search tools).
- `pdf2viking(pdf, viking_uri, ...)` — one-shot: translate + ingest.

The tools run on the DSH **host** (not the agent sandbox), so they have full
network / memory / filesystem access.

> **Note on the plugin skeleton**: the cordis registration and tool-wrapper
> boilerplate are adapted from `@openviking/dsh-memory-plugin` (Apache-2.0).
> See `NOTICE` for the attribution and modified files.

---

## 1. Prerequisites

- **DeepSeek Harness** running (web profile), Node >= 22.
- **pdf2zh with the `--notes` feature** (see §1.1 — the official PyPI release
  does not have it yet), importable by some Python.
- **OpenViking** server running (default `http://127.0.0.1:1933`).

### 1.1 The pdf2zh dependency

This plugin drives pdf2zh's `--notes --notes-format jsonl` pipeline, which is
**not yet in the official PyPI `pdf2zh` release** (it would crash on the unknown
`--notes` argument). Use the **maintainer's fork**, which includes the notes
feature:

```powershell
pip install git+https://github.com/wqy-lab/PDFMathTranslate.git
```

Then point the plugin at that Python:

```powershell
setx PDF2ZH_PYTHON "<python that has pdf2zh installed>"
```

`PDF2ZH_REPO` is **optional**: the plugin bundles its own `notes2viking.py`, and
a pip-installed pdf2zh runs from any directory.

**Alternative (no fork / pip):** apply the bundled patch to a pdf2zh **v1.9.11**
checkout with `.\setup-pdf2zh-notes.ps1 -Repo <checkout>`, then set
`PDF2ZH_REPO` + `PDF2ZH_PYTHON` to it.

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
restart DSH. The agent will then have the three `pdf2zh_*` tools.

---

## 3. Configuration (detailed flow)

### 3.1 Copy the provider template

The plugin reads all translation services from a providers file (never committed;
API keys live there). It looks for it, in order: `PDF2ZH_PROVIDERS_FILE` env,
then `~/.dsh/pdf2zh-providers.json` (default, survives upgrades), then the
plugin directory's `providers.json` (dev). Create it from the template:

```powershell
Copy-Item "<plugin dir>\providers.example.json" "$env:USERPROFILE\.dsh\pdf2zh-providers.json"
```

No env var needed — the plugin auto-reads `~/.dsh/pdf2zh-providers.json`.

### 3.2 Fill in your providers

`providers.json` maps a **name** → a pdf2zh service + model + API env:

```json
{
  "deepseek": {
    "service": "deepseek",
    "model": "deepseek-v4-flash",
    "env": {
      "DEEPSEEK_API_KEY": "sk-你的key",
      "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1"
    }
  },
  "custom": {
    "service": "custom",
    "model": "some-model",
    "env": {
      "CUSTOM_API_KEY": "...",
      "CUSTOM_BASE_URL": "https://你的端点/v1"
    }
  },
  "google": { "service": "google", "model": "", "env": {} }
}
```

Each entry: `service` = pdf2zh translator name (`google`, `deepseek`, `openai`,
`custom`, …), `model` = the model (empty for services without a model), `env` =
environment variables injected into the pdf2zh subprocess (API keys / base URLs).

**Security**: `providers.json` contains plaintext keys — do not commit it.
Add `dsh-pdf2zh/providers.json` to your `.gitignore`.

### 3.3 Point the plugin at your environment (env vars)

| Env var | Meaning | Example |
|---|---|---|
| `PDF2ZH_PYTHON` | Python that can run `-m pdf2zh.pdf2zh` | `C:\path\to\envs\python.exe` |
| `PDF2ZH_REPO` | pdf2zh checkout root (optional; only for patch/editable installs) | `<your pdf2zh checkout>` |
| `PDF2ZH_SERVICE` | Default service (provider name or `service:model`) | `deepseek` |
| `PDF2ZH_LANG_IN` / `PDF2ZH_LANG_OUT` | Source/target language codes | `en` / `zh` |
| `PDF2ZH_SERVER` | OpenViking server base URL | `http://127.0.0.1:1933` |
| `PDF2ZH_PROVIDERS_FILE` | Custom providers.json location | `C:\Users\<you>\.dsh\pdf2zh-providers.json` |
| `PDF2ZH_OPENBLAS_THREADS` | Thread limit fix for scipy-openblas | `1` |

Windows: `setx PDF2ZH_PYTHON "C:\...\python.exe"` then **restart DSH** (setx only
affects new processes).

### 3.4 Verify

Restart DSH, then ask the agent: "list your pdf2zh tools" — you should see the
three `pdf2zh_*` tools. Or run a tiny ingest to confirm the chain.

---

## 4. Usage

```text
「把 <PDF> 翻译并入库到 viking:/resources/papers/<类别>/<id>--<slug>.notes.md，用 deepseek」
```

The agent calls `pdf2viking` (or `pdf2zh_translate` then `pdf2zh_ingest`).

`service` accepts:
1. a provider **name** from `providers.json` (e.g. `deepseek`),
2. a raw `service:model` string (e.g. `deepseek:deepseek-v4-flash`),
3. nothing → uses `PDF2ZH_SERVICE` / config default.

---

## 5. License

Apache-2.0. This plugin's bootstrap skeleton is derived from
`@openviking/dsh-memory-plugin` (Apache-2.0); see `NOTICE` for details and the
list of modified files. It **invokes** pdf2zh (AGPL-3.0) as an external process
and does not incorporate its code; install pdf2zh separately.
