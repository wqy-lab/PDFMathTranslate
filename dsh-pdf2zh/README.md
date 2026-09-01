# dsh-pdf2zh

DeepSeek Harness plugin that exposes the pdf2zh pipeline as native agent tools:

- `pdf2zh_translate(pdf, service, lang_in, lang_out, output)` — translate a PDF and export structured notes JSONL.
- `pdf2zh_ingest(jsonl, viking_uri)` — ingest the JSONL into OpenViking (indexed for `viking_search`).
- `pdf2viking(pdf, viking_uri, ...)` — one-shot translate + ingest.

The tools run on the DSH **host** (not the agent sandbox), so they have full network /
memory / filesystem access — this is what makes the heavy pdf2zh pipeline (ONNX model,
translation API) actually work when invoked by an agent.

## Prerequisites

1. `E:\Project\PDFMathTranslate` — the repo (pdf2zh source + `tools/notes2viking.py`).
2. The `pdftranslate` conda env with pdf2zh installed editable:
   `& "C:\Users\WqYlearnph\.conda\envs\pdftranslate\python.exe" -m pip install -e . --no-deps`
3. `setx OPENBLAS_NUM_THREADS "1"` (fixes the scipy-openblas memory error); the plugin also
   sets it per-subprocess via config, so this is a belt-and-suspenders measure.

## Install

```powershell
dsh plugin --profile web add "file:E:/Project/PDFMathTranslate/dsh-pdf2zh"
```

Then edit `C:\Users\WqYlearnph\.dsh\profiles\web\package.json` and add `"dsh-pdf2zh"`
to the `dsh.profile.bundles` array (next to the other bundles), then:

```powershell
cd C:\Users\WqYlearnph\.dsh\profiles\web
pnpm install
```

Restart DSH (the web app), and the agent will have the three `pdf2zh_*` tools.

## Config (optional overrides)

Defaults live in `config.mjs` and can be overridden via env vars:

| Setting | Env var | Default |
|---|---|---|
| python | `PDF2ZH_PYTHON` | `C:\Users\WqYlearnph\.conda\envs\pdftranslate\python.exe` |
| repo | `PDF2ZH_REPO` | `E:\Project\PDFMathTranslate` |
| server | `PDF2ZH_SERVER` | `http://127.0.0.1:1933` |
| openblas threads | `PDF2ZH_OPENBLAS_THREADS` | `1` |

## Usage (agent prompt)

"把 `E:\AI\rl-tree\papers\generative-rl\OGPO.pdf` 翻译并入库" — the agent calls
`pdf2viking` (with a target viking URI) once and reports the result.
