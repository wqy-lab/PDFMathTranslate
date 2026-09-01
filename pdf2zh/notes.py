"""Intermediate text export for the pdf2zh fast-mode pipeline.

The fast-mode pipeline already splits a PDF into paragraphs during parsing
(``TranslateConverter.receive_layout``), producing per-paragraph source text
(``sstk``), translated text (``news``), positions/sizes (``pstk``) and formula
characters (``var``).  This module turns that in-memory paragraph stream into a
structured Markdown (and optional JSONL) artifact that an external agent can
read to produce chapter-level reading notes.

pdf2zh itself does NOT generate notes here — it only exports the intermediate
text.  Heading detection uses the doclayout ``title`` class (passed in as a
per-paragraph ``is_title`` flag) plus a font-size fallback.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Formula placeholders look like ``{v0}`` (the parser may emit ``{ v0 }`` and
# translators may uppercase the ``v``).
FORMULA_RE = re.compile(r"\{\s*v(\d+)\s*\}", re.IGNORECASE)


@dataclass
class ParagraphRecord:
    """One paragraph as captured by the pipeline, plus its derived structure."""

    page: int  # 0-based page index
    text: str  # source paragraph, formulas inlined as $...$
    translation: str  # translated paragraph, formulas inlined as $...$
    font_size: float  # paragraph font size (PDF points)
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 (PDF coords)
    is_title: bool = False  # doclayout "title" class (or font-size fallback)

    # Filled in during NoteExporter.write() by assign_headings().
    level: int = 0  # heading level 1..3, 0 = body paragraph
    section_path: list[str] = field(default_factory=list)


def render_formula_placeholders(text: str, var: list[list[Any]]) -> str:
    """Replace ``{vN}`` placeholders with the extracted formula text.

    ``var[N]`` is the list of ``LTChar`` objects captured for formula ``N``;
    ``get_text()`` returns their readable unicode.  The result is wrapped in
    ``$...$`` so the export stays valid Markdown.
    """

    def repl(m: re.Match) -> str:
        idx = int(m.group(1))
        if 0 <= idx < len(var):
            body = "".join(ch.get_text() for ch in var[idx])
            return f"${body}$"
        return m.group(0)

    return FORMULA_RE.sub(repl, text)


def _clean(s: str) -> str:
    """Collapse whitespace/newlines so each paragraph stays on one line."""
    return " ".join((s or "").split())


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _apply_section_path(records: list[ParagraphRecord]) -> None:
    """Assign ``section_path`` to every record from the heading hierarchy."""
    path: list[str] = []
    for r in records:
        if r.level > 0:
            path = path[: r.level - 1]
            path.append(_clean(r.text))
            r.section_path = list(path)
        else:
            r.section_path = list(path)


def assign_headings(records: list[ParagraphRecord]) -> None:
    """In-place: set ``level`` and ``section_path`` for each record.

    Headings are the doclayout ``title`` paragraphs, plus any paragraph whose
    font size is notably larger than the body median and short enough to be a
    heading (not emphasized body text).  Distinct heading font sizes are
    clustered into up to three levels (largest = level 1).
    """
    if not records:
        return

    sizes = [r.font_size for r in records if r.font_size and r.font_size > 0]
    body_median = _median(sizes) if sizes else 0.0

    def is_heading(r: ParagraphRecord) -> bool:
        if r.is_title:
            return True
        if body_median <= 0:
            return False
        return r.font_size >= body_median * 1.15 and len(r.text.strip()) < 200

    heading_sizes = sorted(
        {round(r.font_size, 1) for r in records if is_heading(r)},
        reverse=True,
    )

    if not heading_sizes:
        _apply_section_path(records)
        return

    # Largest heading size -> level 1; next distinct sizes -> 2, 3.
    size_to_level = {s: i + 1 for i, s in enumerate(heading_sizes[:3])}
    for r in records:
        if is_heading(r):
            r.level = size_to_level.get(round(r.font_size, 1), 3)

    _apply_section_path(records)


def _yaml_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(ch in s for ch in "\n\"#'{}[]:,&*?|!%@`"):
        return json.dumps(s, ensure_ascii=False)
    return s


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def render_markdown_body(records: list[ParagraphRecord]) -> str:
    """Render records as Markdown body (headings, paragraphs, page markers)."""
    lines = []
    last_page = None
    for r in records:
        if r.page != last_page:
            lines.append("")
            lines.append(f"<!-- ===== page {r.page + 1} ===== -->")
            lines.append("")
            last_page = r.page
        text = _clean(r.text)
        trans = _clean(r.translation)
        if r.level > 0:
            lines.append(f"{'#' * min(r.level, 6)} {text}")
        else:
            lines.append(text)
        if trans and trans != text:
            lines.append(f"> {trans}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_markdown(records: list[ParagraphRecord], meta: dict) -> str:
    """Render records as Markdown with YAML front-matter and page markers."""
    header = ["---"] + [f"{k}: {_yaml_scalar(v)}" for k, v in meta.items()] + ["---", ""]
    return "\n".join(header) + render_markdown_body(records)


def render_jsonl(records: list[ParagraphRecord]) -> str:
    """Render records as JSONL (one object per paragraph, 1-based pages)."""
    out = []
    for r in records:
        d = asdict(r)
        d["page"] = r.page + 1  # 1-based for readability
        d["bbox"] = list(r.bbox)
        out.append(json.dumps(d, ensure_ascii=False))
    return "\n".join(out) + ("\n" if out else "")


_NOTE_SYSTEM_PROMPT_ZH = (
    "你是一位严谨的学术文献精读助手。用户会给你一篇论文的一个章节，其中同时包含"
    "原文和译文：行首以 `> ` 开头的是译文，公式用 `$...$` 包裹，`<!-- page N -->` 是页码标记。"
    "请生成该章节的精读笔记，按以下结构输出（Markdown）：\n"
    "1. **本节核心**：2-4 句话概括本节在论证什么、结论是什么\n"
    "2. **关键概念**：逐条解释本节出现的术语/缩写（术语加粗）\n"
    "3. **重要公式**：列出关键公式并解释每个符号的含义（如无公式可省略本节）\n"
    "4. **要点**：bullet 列表，每条一句话\n"
    "5. **与其他章节的关联**：如能判断，简短说明\n"
    "要求：用中文输出，不要复述原文，只输出笔记内容本身，不要多余的开场白。"
)

_NOTE_SYSTEM_PROMPT_EN = (
    "You are a rigorous academic reading assistant. The user will give you one "
    "section of a paper containing both the original text and its translation: "
    "lines starting with `> ` are the translation, formulas are wrapped in `$...$`, "
    "and `<!-- page N -->` marks page boundaries. Produce structured reading notes "
    "for this section (Markdown):\n"
    "1. **Core idea**: 2-4 sentences on what this section argues and concludes\n"
    "2. **Key concepts**: define the terms/abbreviations (bold the term)\n"
    "3. **Key formulas**: list important formulas and explain their symbols "
    "(omit if none)\n"
    "4. **Bullet points**: one line each\n"
    "5. **Relation to other sections**: if discernible, briefly\n"
    "Output the notes only, no preamble, do not restate the source."
)


class NoteGenerator:
    """Generate chapter-level reading notes by calling a chat-capable LLM.

    ``chat_fn`` is a ``messages -> str`` callable (e.g. a translator's ``chat``
    method). The document is split by top-level section and each section is sent
    to the LLM (sub-chunked by ``chunk_chars`` when it is too long).
    """

    def __init__(
        self,
        chat_fn,
        lang: str = "zh",
        chunk_chars: int = 6000,
        max_tokens: int = 2000,
    ) -> None:
        self.chat_fn = chat_fn
        self.lang = (lang or "zh").lower()
        self.chunk_chars = chunk_chars
        self.max_tokens = max_tokens

    @property
    def system_prompt(self) -> str:
        if self.lang.startswith("en"):
            return _NOTE_SYSTEM_PROMPT_EN
        return _NOTE_SYSTEM_PROMPT_ZH

    def generate(self, records: list[ParagraphRecord], meta: dict) -> str:
        title = _clean(meta.get("source", "document"))
        parts = [f"# {title} 精读笔记\n"]
        for section_title, recs in self._split_sections(records):
            parts.append(self._generate_section(section_title, recs))
        return "\n".join(parts).rstrip() + "\n"

    def _split_sections(self, records):
        sections: list[tuple[str, list[ParagraphRecord]]] = []
        current_key = None
        current_recs: list[ParagraphRecord] = []
        for r in records:
            key = r.section_path[0] if r.section_path else ""
            if key != current_key:
                if current_recs:
                    sections.append((current_key or "前言", current_recs))
                current_key = key
                current_recs = []
            current_recs.append(r)
        if current_recs:
            sections.append((current_key or "前言", current_recs))
        return sections

    def _generate_section(self, title: str, recs: list[ParagraphRecord]) -> str:
        body = render_markdown_body(recs)
        chunks = self._chunk(body)
        notes = []
        for i, chunk in enumerate(chunks):
            user = f"章节标题：{title}\n\n{chunk}"
            if len(chunks) > 1:
                user = f"（第 {i + 1}/{len(chunks)} 部分）\n\n{user}"
            result = self.chat_fn(
                [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user},
                ],
                max_tokens=self.max_tokens,
            )
            notes.append(result)
        return f"## {title}\n\n" + "\n\n".join(notes).strip() + "\n"

    def _chunk(self, text: str) -> list[str]:
        if len(text) <= self.chunk_chars:
            return [text]
        paras = text.split("\n\n")
        chunks: list[str] = []
        cur = ""
        for p in paras:
            if len(cur) + len(p) + 2 > self.chunk_chars and cur:
                chunks.append(cur)
                cur = p
            else:
                cur = f"{cur}\n\n{p}" if cur else p
        if cur:
            chunks.append(cur)
        return chunks


class NoteExporter:
    """Accumulates per-page paragraph records and writes the export files."""

    def __init__(self) -> None:
        self.records: list[ParagraphRecord] = []

    def on_page(self, pageid: int, records: list[ParagraphRecord]) -> None:
        self.records.extend(records)

    @property
    def page_count(self) -> int:
        if not self.records:
            return 0
        return max(r.page for r in self.records) + 1

    def prepare(self, meta: dict) -> dict:
        """Assign headings and fill meta defaults; returns the meta dict."""
        assign_headings(self.records)
        meta = dict(meta)
        meta.setdefault("heading_count", sum(1 for r in self.records if r.level > 0))
        meta.setdefault("exported_at", _now_iso())
        return meta

    def write_markdown(self, output_dir: str, filename: str, meta: dict) -> str:
        """Write the intermediate structured Markdown; returns its path."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"{filename}-notes.md"
        p.write_text(render_markdown(self.records, meta), encoding="utf-8")
        return str(p)

    def write_jsonl(self, output_dir: str, filename: str) -> str:
        """Write the intermediate JSONL export; returns its path."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"{filename}-notes.jsonl"
        p.write_text(render_jsonl(self.records), encoding="utf-8")
        return str(p)

    def write(
        self,
        output_dir: str,
        filename: str,
        meta: dict,
        fmt: str = "md",
    ) -> list[str]:
        """Assign headings, then write Markdown and/or JSONL. Returns paths."""
        meta = self.prepare(meta)
        written: list[str] = []
        if fmt in ("md", "both"):
            written.append(self.write_markdown(output_dir, filename, meta))
        if fmt in ("jsonl", "both"):
            written.append(self.write_jsonl(output_dir, filename))
        return written
