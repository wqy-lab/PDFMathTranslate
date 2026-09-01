import json
import os
import unittest

from pdf2zh.notes import (
    NoteExporter,
    NoteGenerator,
    ParagraphRecord,
    assign_headings,
    render_formula_placeholders,
    render_jsonl,
    render_markdown,
    render_markdown_body,
)


class _Char:
    def __init__(self, t):
        self._t = t

    def get_text(self):
        return self._t


class TestRenderFormulaPlaceholders(unittest.TestCase):
    def test_basic(self):
        var = [[_Char("x"), _Char("+"), _Char("y")]]
        self.assertEqual(
            render_formula_placeholders("a {v0} b", var), "a $x+y$ b"
        )

    def test_spaced_and_case(self):
        var = [[_Char("α")]]
        self.assertEqual(
            render_formula_placeholders("a { V0 } b", var), "a $α$ b"
        )

    def test_out_of_range(self):
        self.assertEqual(
            render_formula_placeholders("a {v0} b", []), "a {v0} b"
        )


class TestAssignHeadings(unittest.TestCase):
    def test_levels_and_paths(self):
        recs = [
            ParagraphRecord(
                page=0, text="Intro", translation="", font_size=20,
                bbox=(0, 0, 0, 0), is_title=True,
            ),
            ParagraphRecord(
                page=0, text="body one", translation="", font_size=11,
                bbox=(0, 0, 0, 0),
            ),
            ParagraphRecord(
                page=0, text="1 Method", translation="", font_size=15,
                bbox=(0, 0, 0, 0), is_title=True,
            ),
            ParagraphRecord(
                page=0, text="1.1 Setup", translation="", font_size=13,
                bbox=(0, 0, 0, 0), is_title=True,
            ),
            ParagraphRecord(
                page=0, text="body two", translation="", font_size=11,
                bbox=(0, 0, 0, 0),
            ),
            ParagraphRecord(
                page=0, text="Results", translation="", font_size=15,
                bbox=(0, 0, 0, 0), is_title=True,
            ),
            ParagraphRecord(
                page=0, text="body three", translation="", font_size=11,
                bbox=(0, 0, 0, 0),
            ),
        ]
        assign_headings(recs)
        self.assertEqual(recs[0].level, 1)
        self.assertEqual(recs[2].level, 2)
        self.assertEqual(recs[3].level, 3)
        self.assertEqual(recs[1].section_path, ["Intro"])
        self.assertEqual(
            recs[4].section_path, ["Intro", "1 Method", "1.1 Setup"]
        )
        self.assertEqual(recs[6].section_path, ["Intro", "Results"])

    def test_no_headings(self):
        recs = [
            ParagraphRecord(
                page=0, text="a", translation="", font_size=11,
                bbox=(0, 0, 0, 0),
            ),
        ]
        assign_headings(recs)
        self.assertEqual(recs[0].level, 0)
        self.assertEqual(recs[0].section_path, [])


class TestRender(unittest.TestCase):
    def test_markdown(self):
        recs = [
            ParagraphRecord(
                page=0, text="Intro", translation="引言", font_size=20,
                bbox=(0, 0, 0, 0), is_title=True, level=1,
                section_path=["Intro"],
            ),
            ParagraphRecord(
                page=0, text="Hello world", translation="你好世界",
                font_size=11, bbox=(0, 0, 0, 0),
            ),
        ]
        md = render_markdown(recs, {"source": "x.pdf"})
        self.assertIn("source: x.pdf", md)
        self.assertIn("# Intro", md)
        self.assertIn("> 引言", md)
        self.assertIn("Hello world", md)
        self.assertIn("> 你好世界", md)
        self.assertIn("page 1", md)

    def test_jsonl(self):
        recs = [
            ParagraphRecord(
                page=0, text="t", translation="", font_size=10,
                bbox=(1, 2, 3, 4),
            ),
        ]
        jl = render_jsonl(recs)
        obj = json.loads(jl.strip().splitlines()[0])
        self.assertEqual(obj["page"], 1)
        self.assertEqual(obj["bbox"], [1, 2, 3, 4])


class TestNoteExporter(unittest.TestCase):
    def test_write(self):
        import shutil
        from pathlib import Path

        # Use a workspace subdir via Path.mkdir (mkdtemp-created dirs can be
        # write-denied under some sandboxes).
        d = str(Path(os.getcwd()) / "_test_notes_tmp")
        shutil.rmtree(d, ignore_errors=True)
        Path(d).mkdir(parents=True, exist_ok=True)
        try:
            exporter = NoteExporter()
            exporter.on_page(
                0,
                [
                    ParagraphRecord(
                        page=0, text="Head", translation="", font_size=18,
                        bbox=(0, 0, 0, 0), is_title=True,
                    ),
                    ParagraphRecord(
                        page=0, text="Body", translation="", font_size=11,
                        bbox=(0, 0, 0, 0),
                    ),
                ],
            )
            paths = exporter.write(d, "doc", {"source": "doc.pdf"}, "both")
            md = Path(paths[0])
            jl = Path(paths[1])
            self.assertTrue(md.exists())
            self.assertTrue(jl.exists())
            self.assertIn("heading_count: 1", md.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestNoteGenerator(unittest.TestCase):
    def _records(self):
        recs = [
            ParagraphRecord(
                page=0, text="Intro", translation="", font_size=20,
                bbox=(0, 0, 0, 0), is_title=True,
            ),
            ParagraphRecord(
                page=0, text="body one", translation="", font_size=11,
                bbox=(0, 0, 0, 0),
            ),
            ParagraphRecord(
                page=1, text="Method", translation="", font_size=20,
                bbox=(0, 0, 0, 0), is_title=True,
            ),
            ParagraphRecord(
                page=1, text="body two", translation="", font_size=11,
                bbox=(0, 0, 0, 0),
            ),
        ]
        assign_headings(recs)
        return recs

    def test_generate_splits_by_section(self):
        recs = self._records()
        calls = []

        def chat_fn(messages, max_tokens=None):
            calls.append(messages)
            return "NOTE"

        gen = NoteGenerator(chat_fn)
        out = gen.generate(recs, {"source": "doc.pdf"})
        self.assertEqual(len(calls), 2)
        self.assertIn("## Intro", out)
        self.assertIn("## Method", out)
        self.assertIn("NOTE", out)

    def test_chunk_large_section(self):
        gen = NoteGenerator(lambda m, **k: "x", chunk_chars=20)
        chunks = gen._chunk("aaaa\n\nbbbb\n\ncccc\n\ndddd")
        self.assertGreater(len(chunks), 1)

    def test_render_body_has_no_frontmatter(self):
        recs = self._records()
        body = render_markdown_body(recs)
        self.assertNotIn("---", body)


if __name__ == "__main__":
    unittest.main()
