<#
.SYNOPSIS
    Patch a pdf2zh checkout with the --notes feature required by dsh-pdf2zh.

.DESCRIPTION
    1. Locates (or clones) a PDFMathTranslate checkout.
    2. Applies pdf2zh-notes.patch (targets pdf2zh v1.9.11).
    3. Creates providers.json from providers.example.json (plugin dir).
    4. Prints the env vars to set (PDF2ZH_REPO / PDF2ZH_PYTHON).

.EXAMPLE
    .\setup-pdf2zh-notes.ps1 -Repo "E:\path\to\PDFMathTranslate"
    .\setup-pdf2zh-notes.ps1            # clones into ./pdf2zh-checkout
#>
param(
    [string]$Repo = ""
)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

# --- 1. locate or clone the checkout ---
if (-not $Repo) {
    $Repo = Join-Path $here "pdf2zh-checkout"
    if (-not (Test-Path (Join-Path $Repo ".git"))) {
        Write-Host "Cloning PDFMathTranslate into $Repo ..."
        git clone --depth 1 https://github.com/Byaidu/PDFMathTranslate.git $Repo
    }
}
if (-not (Test-Path (Join-Path $Repo ".git"))) {
    throw "$Repo is not a git checkout of PDFMathTranslate."
}

# --- 2. apply the patch ---
$patch = Join-Path $here "pdf2zh-notes.patch"
Push-Location $Repo
try {
    git apply --check $patch 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "pdf2zh-notes.patch does not apply cleanly. It targets pdf2zh v1.9.11; if your checkout is newer, run: git checkout <v1.9.11-tag-or-commit> and retry."
    }
    git apply $patch
    if ($LASTEXITCODE -ne 0) { throw "git apply failed." }
    Write-Host "Patched pdf2zh with --notes support."
} finally {
    Pop-Location
}

# --- 3. create providers.json from example ---
$providers = Join-Path $here "providers.json"
if (-not (Test-Path $providers)) {
    Copy-Item (Join-Path $here "providers.example.json") $providers
    Write-Host "Created providers.json - fill in your API keys."
}

# --- 4. print next steps ---
Write-Host ""
Write-Host "Next steps:"
Write-Host "  setx PDF2ZH_REPO   `"$Repo`""
Write-Host "  setx PDF2ZH_PYTHON `"<python that can run -m pdf2zh.pdf2zh>`""
Write-Host "  restart DSH"
