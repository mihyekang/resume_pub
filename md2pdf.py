"""Markdown -> PDF, with mermaid diagrams baked in as static SVG.

Letting one page render every diagram and then printing it races mermaid:
Chrome snapshots mid-render, some diagrams come out empty and the rest pile up
on a single page. Raising --virtual-time-budget does not help; it is not what
the renderer waits on.

So each diagram is rendered on its own minimal page, which is reliable, and the
resulting SVG is substituted back into the document. The page that gets printed
contains no script at all.

Usage: python md2pdf.py <input.md> <output.pdf>
"""

import io
import os
import re
import subprocess
import sys
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"

# A4 minus the page margins, in CSS px at 96dpi. The height is held well under
# the page so a diagram still fits once its heading and intro sit above it.
MAX_W, MAX_H = 680, 620

ONE = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<div class="mermaid">
%s
</div>
<script type="module">
  import mermaid from "%s";
  mermaid.initialize({
    startOnLoad: true, theme: "base",
    flowchart: { useMaxWidth: true, htmlLabels: true },
    themeVariables: { fontFamily: "NanumGothic, Malgun Gothic, sans-serif", fontSize: "13px" }
  });
</script></body></html>"""


def chrome(args, capture=False):
    profile = os.path.join(tempfile.gettempdir(), "md2pdf-chrome")
    base = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
            "--user-data-dir=" + profile]
    return subprocess.run(base + args, capture_output=capture, timeout=180)


def size_svg(tag):
    """Mermaid emits width="100%" and no height, so the print layout has nothing
    to lay out against. Write the dimensions in, scaled to fit one page."""
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', tag)
    if not box:
        return tag
    w, h = float(box.group(1)), float(box.group(2))
    scale = min(1.0, MAX_W / w, MAX_H / h)
    for attr in ("width", "height", "style"):
        tag = re.sub(r'\s%s="[^"]*"' % attr, "", tag)
    return tag[:-1] + ' width="%d" height="%d">' % (round(w * scale), round(h * scale))


def render(source, tmp, i):
    """Render one diagram on its own page and return its <svg> markup."""
    page = os.path.join(tmp, "d%d.html" % i)
    io.open(page, "w", encoding="utf-8", newline="").write(ONE % (source, CDN))
    res = chrome(["--dump-dom", "--virtual-time-budget=20000",
                  "file:///" + page.replace("\\", "/")], capture=True)
    dom = res.stdout.decode("utf-8", errors="replace")
    m = re.search(r"<svg\b[^>]*viewBox=\"0 0 [\d.]+ [\d.]+\"[^>]*>.*?</svg>", dom, re.DOTALL)
    if not m:
        sys.exit("diagram %d failed to render" % (i + 1))
    svg = m.group(0)
    return size_svg(re.match(r"<svg\b[^>]*>", svg).group(0)) + svg[svg.index(">") + 1:]


def keep_with_heading(body):
    """Tie each heading to the diagram that belongs to it, so the heading is not
    left stranded at the foot of a page while its figure starts the next one.

    A heading only claims the diagram directly beneath it: if another heading
    intervenes, the diagram belongs to that one instead and the pair is left
    alone."""
    heads = [m for m in re.finditer(r"<h[23]\b[^>]*>.*?</h[23]>", body, re.DOTALL)]
    # By now each diagram is an inline <svg> whose labels contain <div>s of
    # their own, so match through </svg> rather than to the first </div>.
    figs = [m for m in re.finditer(
        r'<div class="mermaid"><svg\b.*?</svg></div>|<p><img\b[^>]*/?></p>', body, re.DOTALL)]

    spans = []
    for fig in figs:
        above = [h for h in heads if h.end() <= fig.start()]
        if not above:
            continue
        owner = above[-1]
        if re.search(r"<h[1-6]\b", body[owner.end():fig.start()]):
            continue  # something else sits in between; leave this one alone

        # A section heading whose own text is only a short intro before a
        # sub-heading would otherwise be stranded, so pull it in too.
        if len(above) > 1:
            parent = above[-2]
            gap = body[parent.end():owner.start()]
            if not re.search(r"<(table|ul|ol|img|div)\b", gap) and len(gap) < 500:
                owner = parent

        spans.append((owner.start(), fig.end()))

    for start, end in reversed(spans):
        body = (body[:start] + '<div class="keep">' + body[start:end]
                + "</div>" + body[end:])
    return body


def main():
    src, out_pdf = sys.argv[1], os.path.abspath(sys.argv[2])
    tmp = tempfile.mkdtemp(prefix="md2pdf-")
    html = os.path.join(tmp, "page.html")
    final = os.path.join(tmp, "final.html")

    subprocess.run([sys.executable, os.path.join(HERE, "md2html.py"), src, html],
                   check=True, capture_output=True)
    body = io.open(html, encoding="utf-8").read()

    blocks = list(re.finditer(r'<div class="mermaid">(.*?)</div>', body, re.DOTALL))
    for i, m in enumerate(reversed(blocks)):
        svg = render(m.group(1).strip(), tmp, len(blocks) - 1 - i)
        body = body[:m.start()] + '<div class="mermaid">' + svg + "</div>" + body[m.end():]

    body = re.sub(r"<script type=\"module\">.*?</script>", "", body, flags=re.DOTALL)
    # An empty zero-height div is collapsed and the break ignored, so move
    # the marker onto the heading that follows it.
    body = re.sub(r'<div class="pagebreak"></div>\s*<h([1-6])>',
                  r'<h\1 class="pagebreak">', body)
    body = keep_with_heading(body)
    io.open(final, "w", encoding="utf-8", newline="").write(body)

    # Chrome cannot overwrite the file while a viewer holds it open, and says so
    # only on stderr, so check that the file actually moved rather than trusting
    # the run.
    before = os.path.getmtime(out_pdf) if os.path.exists(out_pdf) else 0
    chrome(["--no-pdf-header-footer", "--print-to-pdf=" + out_pdf,
            "--virtual-time-budget=15000", "file:///" + final.replace("\\", "/")])
    if not os.path.exists(out_pdf) or os.path.getmtime(out_pdf) <= before:
        sys.exit("could not write %s -- is it open in a viewer?" % out_pdf)
    print("pdf written: %s  (%d diagrams)" % (out_pdf, len(blocks)))


if __name__ == "__main__":
    main()
