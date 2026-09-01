#!/usr/bin/env python3
"""Convert pdf2zh's ``-notes.jsonl`` into an OpenViking-ingestible Markdown
and ingest it through the OpenViking server's REST API directly.

No ``ov`` CLI / ``ovcli.conf`` is needed: the script POSTs to the local
server's ``/api/v1/content/write`` endpoint, which writes the resource file AND
runs semantic/vector indexing, making it immediately retrievable via
``viking_search``.

Usage:
  python tools/notes2viking.py D:/paper-notes.jsonl \
      --to <viking-uri>            # dry-run: writes the .md, prints the call
  python tools/notes2viking.py D:/paper-notes.jsonl \
      --to <viking-uri> --run      # also ingest via the server API

The target is a viking namespace path such as
    <scheme>://resources/papers/generative-rl/2605.03065--ogpo.notes.md
where <scheme> is the literal string "viking" (this script's source keeps the
scheme out of literal form so the file can be written by tooling that treats
that prefix as a virtual path).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SERVER = "http://127.0.0.1:1933"


def render_viking_markdown(records: list[dict]) -> str:
    """Render one-section-per-``##``, one-paragraph-per-line Markdown.

    Real headings keep their level (``#``/``##``/``###``); body paragraphs are
    grouped under a ``## section`` line and prefixed with a ``[p.N]`` page
    marker so retrieved chunks carry a citation back to the PDF page.
    """
    lines: list[str] = []
    last_section: str | None = None
    for r in records:
        sec = " / ".join(r.get("section_path") or [])
        page = r.get("page", "?")
        text = (r.get("text") or "").strip()
        trans = (r.get("translation") or "").strip()
        level = int(r.get("level") or 0)

        if level > 0:
            lines.append(f"{'#' * min(level, 6)} {text}")
            last_section = sec
            lines.append("")
            continue

        if sec and sec != last_section:
            lines.append(f"## {sec}")
            lines.append("")
            last_section = sec

        lines.append(f"[p.{page}] {text}")
        if trans and trans != text:
            lines.append(f"> {trans}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _api_call(server: str, path: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        server + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
        except Exception:
            detail = {"error": {"message": e.reason or str(e)}}
        return e.code, detail


def ingest(
    uri: str,
    content: str,
    server: str = DEFAULT_SERVER,
    wait: bool = True,
) -> tuple[int, dict]:
    """Create-or-replace a resource and index it. Returns (status, result)."""
    status, result = _api_call(server, "/api/v1/content/write", {
        "uri": uri,
        "content": content,
        "mode": "create",
        "wait": wait,
    })
    if status == 404:  # file already exists -> replace it
        status, result = _api_call(server, "/api/v1/content/write", {
            "uri": uri,
            "content": content,
            "mode": "replace",
            "wait": wait,
        })
    return status, result


def set_tags(uri: str, tag: str, server: str = DEFAULT_SERVER) -> tuple[int, dict]:
    status, result = _api_call(server, "/api/v1/content/set_tags", {
        "uri": uri,
        "tags": [tag],
    })
    return status, result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("jsonl", help="path to the pdf2zh -notes.jsonl file")
    p.add_argument("--to", help="exact target viking URI (e.g. viking:/<namespace>/<cat>/<id>.notes.md)")
    p.add_argument("--output", help="local .md output path (default: <jsonl-stem>.viking.md)")
    p.add_argument("--server", default=DEFAULT_SERVER, help="openviking server base URL")
    p.add_argument("--tag", help="k=v retrieval tag to apply after ingest")
    p.add_argument("--no-wait", action="store_true", help="do not wait for indexing")
    p.add_argument("--run", action="store_true", help="actually ingest via the server API (default: dry-run)")
    args = p.parse_args(argv)

    src = Path(args.jsonl)
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    records = [
        json.loads(line)
        for line in src.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        print("error: no records in jsonl", file=sys.stderr)
        return 1

    md = render_viking_markdown(records)
    out = Path(args.output) if args.output else src.with_suffix("").with_suffix(".viking.md")
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out} ({len(records)} paragraphs, {len(md)} chars)")

    if not args.to:
        print("hint: pass --to <viking-uri> to target the import", file=sys.stderr)
        return 0

    if not args.run:
        print(f"(dry-run; would POST {len(md)} chars to {args.server}/api/v1/content/write)")
        print(f"  uri: {args.to}")
        print("add --run to ingest")
        return 0

    status, result = ingest(args.to, md, args.server, wait=not args.no_wait)
    if status != 200:
        err = result.get("error", {})
        print(f"error: HTTP {status} {err.get('message', '')}", file=sys.stderr)
        return 1

    r = result.get("result", {})
    print("ingested:", r.get("uri"))
    print("semantic_status:", r.get("semantic_status"), "| vector_status:", r.get("vector_status"))

    if args.tag:
        tstatus, tres = set_tags(args.to, args.tag, args.server)
        if tstatus == 200:
            print("tagged:", args.tag)
        else:
            print(f"warning: set_tags failed HTTP {tstatus}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
