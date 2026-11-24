# -*- coding: utf-8 -*-
"""notesbrevity: build a styled Chinese lecture-note PDF.

Usage:
    python build.py                 # build the bundled example
    python build.py mynotes         # build mynotes/notes.json
    python build.py mynotes -o out.pdf

Pipeline:
    HTML fragments + KaTeX  ->  headless Chrome  ->  PyMuPDF
    (layout)                    (print to PDF)       (header/footer, outline, font subset)
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
KATEX = ROOT / "assets" / "katex"
TEMPLATE_CSS = ROOT / "templates" / "style.css"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def find_chrome() -> str:
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("msedge")
    if found:
        return found
    raise RuntimeError(
        "Chrome/Edge not found. Install Chrome, or add its executable to "
        "CHROME_CANDIDATES in build.py."
    )


def find_font() -> str | None:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None  # PyMuPDF's built-in "china-s" font is used as fallback


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def clean_title(raw: str) -> str:
    """Turn the inner HTML of <h1> into plain text for headers/bookmarks."""
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_lib.unescape(raw)
    raw = raw.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", raw).strip()


def chapter_titles(body: str) -> list[str]:
    pattern = re.compile(
        r'<div\s+class="chapter-band"[^>]*>.*?<h1[^>]*>(.*?)</h1>',
        re.S | re.I,
    )
    return [clean_title(m) for m in pattern.findall(body)]


# --------------------------------------------------------------------------- #
# HTML assembly
# --------------------------------------------------------------------------- #
def build_html(project: Path, cfg: dict) -> tuple[Path, list[str]]:
    files = cfg.get("files") or []
    if not files:
        raise ValueError(f"{project / 'notes.json'} needs a non-empty 'files' list")

    body = "\n".join(read_text(project / f) for f in files)
    css = read_text(TEMPLATE_CSS)
    title = cfg.get("title", "讲义")
    subtitle = cfg.get("subtitle", "")
    lang = cfg.get("lang", "zh-CN")

    katex_css = (KATEX / "katex.min.css").resolve().as_uri()
    katex_js = (KATEX / "katex.min.js").resolve().as_uri()
    auto_js = (KATEX / "contrib" / "auto-render.min.js").resolve().as_uri()

    doc = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{html_lib.escape(title)}</title>
<meta name="description" content="{html_lib.escape(subtitle)}">
<link rel="stylesheet" href="{katex_css}">
<style>
{css}
</style>
</head>
<body>
{body}
<script src="{katex_js}"></script>
<script src="{auto_js}"></script>
<script>
renderMathInElement(document.body, {{
  delimiters: [
    {{left: "$$", right: "$$", display: true}},
    {{left: "$",  right: "$",  display: false}}
  ],
  throwOnError: false
}});
</script>
</body>
</html>
"""
    html_path = project / "combined.html"
    html_path.write_text(doc, encoding="utf-8")
    return html_path, chapter_titles(body)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def print_pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = find_chrome()
    profile = tempfile.mkdtemp(prefix="notesbrevity-chrome-")
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-pdf-header-footer",
        "--allow-file-access-from-files",
        f"--user-data-dir={profile}",
        f"--print-to-pdf={pdf_path}",
        "--virtual-time-budget=20000",
        html_path.resolve().as_uri(),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not pdf_path.exists():
        raise RuntimeError("Chrome failed to produce a PDF:\n" + (r.stderr or r.stdout))


def find_chapter_page(doc: pymupdf.Document, title: str, start: int) -> int | None:
    """Find the page where the chapter title is rendered as a big heading.

    A plain text search is not enough: the front matter may mention the title
    in small body text. Chapter-band <h1> is ~21 pt, body text is ~10.5 pt.
    """
    needle = re.sub(r"\s+", "", title)[:20]
    if not needle:
        return None
    for pno in range(start, len(doc)):
        for block in doc[pno].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = re.sub(r"\s+", "", "".join(s["text"] for s in spans))
                if needle in text and spans and max(s["size"] for s in spans) >= 14:
                    return pno
    # fallback: ordinary text search
    for pno in range(start, len(doc)):
        if doc[pno].search_for(title[:24]):
            return pno
    return None


def stamp(pdf_path: Path, out_path: Path, cfg: dict, titles: list[str]) -> int:
    doc = pymupdf.open(pdf_path)
    n = len(doc)
    base_header = cfg.get("header") or cfg.get("title") or "讲义"
    font_file = find_font()
    font_args = (
        {"fontname": "CJK", "fontfile": font_file}
        if font_file
        else {"fontname": "china-s"}
    )

    # Locate chapter start pages before drawing anything.
    starts: list[tuple[int, str]] = []
    toc: list[list] = []
    search_from = 0
    for title in titles:
        found = find_chapter_page(doc, title, search_from)
        if found is not None:
            starts.append((found, title))
            toc.append([1, title, found + 1])
            search_from = found + 1

    for i, page in enumerate(doc):
        w, h = page.rect.width, page.rect.height
        left, right = 54, w - 54
        header = base_header
        for pno, title in starts:
            if i >= pno:
                header = f"{base_header} · {title}"
        page.insert_text(
            (left, 35), header, fontsize=8,
            color=(0.42, 0.42, 0.42), **font_args,
        )
        page.draw_line((left, 42), (right, 42), color=(0.72, 0.72, 0.72), width=0.45)
        label = f"- {i + 1} -"
        tw = pymupdf.get_text_length(label, fontname="helv", fontsize=8.5)
        page.insert_text(
            ((w - tw) / 2, h - 32), label, fontsize=8.5,
            color=(0.42, 0.42, 0.42), fontname="helv",
        )

    if toc:
        doc.set_toc(toc)
    doc.set_metadata({
        "title": cfg.get("title", "讲义"),
        "author": cfg.get("author", ""),
        "subject": cfg.get("subtitle", ""),
        "creator": "notesbrevity (HTML + KaTeX + Chrome + PyMuPDF)",
    })
    if hasattr(doc, "subset_fonts"):
        try:
            doc.subset_fonts()  # 14 MB -> ~2 MB on the bundled example
        except Exception:
            pass
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    return n


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build a styled Chinese lecture-note PDF.")
    ap.add_argument("project", nargs="?", default="example",
                    help="project directory containing notes.json (default: example)")
    ap.add_argument("-o", "--output", default=None,
                    help="output PDF path (default: notes.json 'output')")
    args = ap.parse_args(argv)

    project = Path(args.project).resolve()
    config_path = project / "notes.json"
    if not config_path.exists():
        raise SystemExit(f"notes.json not found in {project}")
    cfg = json.loads(read_text(config_path))

    html_path, titles = build_html(project, cfg)
    tmp = Path(tempfile.gettempdir()) / "notesbrevity-build.pdf"
    if tmp.exists():
        tmp.unlink()
    print_pdf(html_path, tmp)

    out = Path(args.output).resolve() if args.output else project / cfg.get("output", "notes.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    pages = stamp(tmp, out, cfg, titles)
    print(f"OK  {pages} pages  ->  {out}")


if __name__ == "__main__":
    main()
