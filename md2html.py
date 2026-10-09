import html as html_mod
import os
import re
import sys
import urllib.parse

import markdown

src, dst = sys.argv[1], sys.argv[2]

with open(src, encoding="utf-8") as f:
    text = f.read()

# GitHub parses a pair of single tildes as strikethrough, so date ranges in the
# source are written as \~. Python-Markdown does not treat ~ as an escapable
# character and would print the backslash, so unescape before converting.
text = text.replace("\\~", "~")

body = markdown.markdown(text, extensions=["tables", "sane_lists", "fenced_code"])

# Python-Markdown renders ```mermaid as an escaped <pre><code> block. Mermaid
# needs the raw source inside <div class="mermaid">, so unwrap and unescape it.
def unwrap_mermaid(html_body):
    def repl(m):
        return '<div class="mermaid">' + html_mod.unescape(m.group(1)) + "</div>"

    return re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        repl,
        html_body,
        flags=re.DOTALL,
    )


body = unwrap_mermaid(body)


def absolute_images(html_body):
    """Image paths are relative to the markdown file, but the HTML is written to
    a temp directory, so they would not resolve. Point them at the real files."""
    base = os.path.dirname(os.path.abspath(src))

    def repl(m):
        path = m.group(1)
        if re.match(r"^[a-z]+:|^/", path):
            return m.group(0)
        full = os.path.normpath(os.path.join(base, path))
        if not os.path.exists(full):
            sys.exit("image not found: " + full)
        # Keep the drive colon and separators intact; escape only the rest.
        return 'src="file:///%s"' % urllib.parse.quote(full.replace("\\", "/"), safe="/:")

    return re.sub(r'src="([^"]+)"', repl, html_body)

body = absolute_images(body)
has_mermaid = 'class="mermaid"' in body

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
body {
  font-family: "Malgun Gothic", "맑은 고딕", -apple-system, sans-serif;
  font-size: 10.2pt; line-height: 1.58; color: #1a1a1a;
  margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 {
  font-size: 21pt; font-weight: 700; margin: 0 0 4pt; letter-spacing: -0.4pt;
  padding-bottom: 7pt; border-bottom: 2.2pt solid #1a1a1a;
}
h1 + p { font-size: 11pt; color: #444; margin: 7pt 0 3pt; font-weight: 600; }
h2 {
  font-size: 13.5pt; font-weight: 700; margin: 20pt 0 8pt; padding-bottom: 4pt;
  border-bottom: 1pt solid #c8c8c8; break-after: avoid; page-break-after: avoid;
}
h3 {
  font-size: 11.5pt; font-weight: 700; margin: 14pt 0 5pt; color: #111;
  break-after: avoid; page-break-after: avoid;
}
h4 {
  font-size: 10.6pt; font-weight: 700; margin: 12pt 0 4pt; color: #222;
  padding-left: 7pt; border-left: 3pt solid #555;
  break-after: avoid; page-break-after: avoid;
}
p { margin: 5pt 0; text-align: justify; }
/* A bold-only line (결과, 회고: …) labels the block below it; keep them together. */
p:has(> strong:only-child) { break-after: avoid; page-break-after: avoid; }
ul { margin: 4pt 0 8pt; padding-left: 17pt; }
li { margin: 2.5pt 0; }
strong { font-weight: 700; color: #000; }
a { color: #1a1a1a; text-decoration: none; border-bottom: 0.5pt dotted #888; }
code {
  font-family: Consolas, "D2Coding", monospace; font-size: 9pt;
  background: #f0f0f0; padding: 0.5pt 3pt; border-radius: 2pt;
}
img { max-width: 100%; max-height: 600px; height: auto; display: block; margin: 8pt auto; }
table {
  width: 100%; border-collapse: collapse; margin: 7pt 0 10pt; font-size: 9.3pt;
  break-inside: avoid; page-break-inside: avoid;
}
th {
  background: #ececec; text-align: left; font-weight: 700;
  padding: 5pt 7pt; border: 0.6pt solid #b8b8b8;
}
td { padding: 5pt 7pt; border: 0.6pt solid #cfcfcf; vertical-align: top; }
h2, h3, h4 { break-inside: avoid; page-break-inside: avoid; }
li, tr { break-inside: avoid; page-break-inside: avoid; }
"""

MERMAID_CSS = """
.mermaid { break-inside: avoid; page-break-inside: avoid; margin: 10pt 0 14pt; text-align: center; }
.mermaid svg { max-width: 100%; }
.keep { break-inside: avoid; page-break-inside: avoid; }
/* <div class="pagebreak"></div> in the markdown starts a new page here. */
.pagebreak { break-before: page; page-break-before: always; }
"""

# Rendered client-side by Chrome before --print-to-pdf captures the page.
MERMAID_JS = """
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  mermaid.initialize({
    startOnLoad: true,
    theme: "base",
    flowchart: { useMaxWidth: true, htmlLabels: true },
    themeVariables: { fontFamily: "Malgun Gothic, sans-serif", fontSize: "13px" }
  });
  await mermaid.run();
  document.title = document.title;  // settle before print capture
</script>
"""

html = (
    '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
    "<title>강미혜 경력기술서</title><style>" + CSS
    + (MERMAID_CSS if has_mermaid else "")
    + "</style></head><body>"
    + body
    + (MERMAID_JS if has_mermaid else "")
    + "</body></html>"
)

with open(dst, "w", encoding="utf-8") as f:
    f.write(html)

print("html written:", dst)
