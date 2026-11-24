---
name: notesbrevity
description: Turn lecture notes or English course notes into a polished Chinese lecture-note PDF. Use when the user asks for 讲义、复习笔记、course-notes rewrite, chapter summaries, or a printable study PDF with definitions, examples, and exercises.
---

# notesbrevity

Build a print-ready Chinese lecture-note PDF from HTML fragments using
**HTML + KaTeX + headless Chrome + PyMuPDF**. No LaTeX install, no network.

Let `SKILL_DIR` be the directory containing this `SKILL.md`. It contains a working
engine, a stylesheet, templates, a vendored KaTeX, and a two-chapter demo.

## When to use

- “把这些 course notes 做成中文讲义”
- “为第 4–8 章写一份复习讲义 PDF”
- “把这份英文笔记整理成定义 + 例题 + 练习的形式”
- “重排/续写已有的中文讲义”

## 1. Look at the reference first

Read these before writing:

1. `$SKILL_DIR/templates/style.css` — colours, boxes, page rules.
2. `$SKILL_DIR/templates/chapter.html` — the exact section skeleton.
3. `$SKILL_DIR/example/example.pdf` — what good output looks like.

If the user has an existing lecture PDF in the same style, match its structure
and tone; do not redesign it.

## 2. Scaffold a project

```bash
mkdir mynotes
cp "$SKILL_DIR/templates/front.html" mynotes/
cp "$SKILL_DIR/templates/chapter.html" mynotes/
```

Create `mynotes/notes.json`:

```json
{
  "title": "课程讲义",
  "subtitle": "第一章 – 第三章：主题一 · 主题二",
  "header": "课程讲义",
  "author": "",
  "output": "课程讲义.pdf",
  "files": ["front.html", "ch1.html", "ch2.html"]
}
```

- `files` order is page order.
- `header` is the base running header; each chapter title is appended
  automatically.
- `output` is relative to the project directory.

## 3. Read the source notes

Extract text rather than guessing:

```bash
pdftotext -enc UTF-8 -layout source.pdf source.txt
```

For each source section, collect only: definitions, theorems, algorithms,
worked examples, and the assumptions they need. Do not read the whole PDF
linearly if it is long; grep for `Definition`, `Theorem`, `Lemma`, `Example`,
`Algorithm`, `Abstract`.

## 4. Write the chapters

One HTML file per chapter, starting with:

```html
<section class="chapter" id="ch1">
<div class="chapter-band">
  <div class="cnum">CHAPTER 1</div>
  <h1>第一章　章标题</h1>
  <div class="csub">§1.1 ...　§1.2 ...</div>
</div>
```

The `<h1>` inside `.chapter-band` is used for the running header and the PDF
bookmark. Keep it plain text (no math).

Within each section, use this order:

1. `【通俗理解】` — a picture or analogy first.
2. `【定义】/【定理】` — complete conditions and conclusion.
3. `【证明思路】` — the key idea only; full proof lives in the source notes.
4. `【例N】` + `【解】` — concrete numbers, every step checkable.
5. `【练习N】` + `【答案】` — answer in a separate green box.
6. `【易错提醒】` — 1–3 real traps.

Every chapter ends with:

```html
<h2 class="sec summary">本章小结</h2>
<table>...</table>
<div class="box note">
  <div class="lab">【一页纸记忆】</div>
  ...
</div>
```

`summary` forces a fresh page so the table and memory sheet stay together.

### Box classes

| Class | Use |
|---|---|
| `box note` | instructions, one-page memory |
| `box info` | chapter guide, remarks |
| `box intuition` | plain-language explanation |
| `box proof` | proof idea |
| `box keybox` | definition / theorem / algorithm |
| `box solution` | worked solution (grey) |
| `box answer` | exercise answer (green) |
| `box warn` | common mistakes (red) |

## 5. Math rules

- Inline `$...$`, display `$$...$$`.
- Matrices: `\begin{bmatrix}1&2\\3&4\end{bmatrix}`.
- In HTML, **never** write `<`; use `\lt` in math and `&lt;` in prose.
- Write raw `&` inside matrices (not `&amp;`).
- Keep Chinese outside `\text{}`; KaTeX font fallback for CJK is unreliable.
- Long equations: `\begin{aligned}...\end{aligned}` or split into display lines.

## 6. Build

```bash
python "$SKILL_DIR/build.py" mynotes
```

To build the bundled demo:

```bash
python "$SKILL_DIR/build.py" "$SKILL_DIR/example"
```

Output goes to `mynotes/<output>`.

## 7. Verify before delivering

1. Page count and bookmarks:

   ```python
   import pymupdf
   d = pymupdf.open("mynotes/out.pdf")
   print(len(d), d.get_toc())
   ```

2. No KaTeX errors: search the PDF text for `ParseError`; open `combined.html`
   and look for red formulas.
3. Render pages to PNG (`page.get_pixmap(dpi=90).save(...)`) and check:
   matrices not overflowing, boxes not split, tables not clipped, headers and
   footers present, chapter starts on a new page.
4. Check for near-empty pages (fewer than ~500 characters). Usually caused by a
   big box that cannot fit; split the box or move content.

## 8. Common problems

- **KaTeX not rendering** — wrong delimiter or missing `assets/katex/`.
  Only `$...$` / `$$...$$` are enabled.
- **Chrome produces no PDF** — use an absolute `--print-to-pdf` path and a
  fresh `--user-data-dir`; the script already does both.
- **Chinese boxes/tofu** — install Microsoft YaHei / PingFang / Noto Sans CJK,
  or rely on PyMuPDF's `china-s` fallback.
- **Wrong running header** — the chapter `<h1>` is not inside `.chapter-band`,
  or the title appears in body text at a large size.
- **Blank page before a chapter** — `.chapter` has `break-before: page`; this is
  intentional. Do not remove it.
- **Huge PDF** — keep `doc.subset_fonts()` before saving.

## Output standard

Deliver a PDF whose pages look like the demo: navy chapter bands, amber
“通俗理解” boxes, blue definition boxes, grey solutions, green answers, red
warnings, a summary table per chapter, and a one-page memory sheet. Content must
be technically correct and every example recomputed by hand.
