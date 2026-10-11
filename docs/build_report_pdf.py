"""Render docs/Nidaan_IA2_Report.md to docs/Nidaan_IA2_Report.html and .pdf (A4) and print the page count.

Requirements (not project dependencies): `pip install markdown==3.7 pypdf==5.1.0` and Google Chrome.
Mermaid diagrams are rendered by mermaid.js loaded from cdn.jsdelivr.net, so a network connection is needed.
Screenshots referenced in the report are read from docs/screenshots/; a missing file is rendered as a clearly
marked "screenshot pending" box, never as a substitute image.

Usage: python docs/build_report_pdf.py [--chrome PATH]
"""
from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys

import markdown

DOCS = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(DOCS, "Nidaan_IA2_Report.md")
OUT_HTML = os.path.join(DOCS, "Nidaan_IA2_Report.html")
OUT_PDF = os.path.join(DOCS, "Nidaan_IA2_Report.pdf")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm;
  @bottom-left { content: "K. J. Somaiya School of Engineering"; font: 8pt 'Times New Roman', serif; }
  @bottom-right { content: "Page " counter(page); font: 8pt 'Times New Roman', serif; } }
body { font-family: 'Times New Roman', Times, serif; font-size: 10.5pt; line-height: 1.24; color: #111; }
h1 { font-size: 17pt; text-align: center; font-style: italic; margin: 0 0 4pt; }
h2 { font-size: 13pt; margin: 12pt 0 4pt; }
h2.label { font-size: 11.5pt; font-style: italic; margin-top: 8pt; }
h2.center { text-align: center; font-size: 15pt; margin-top: 16pt; }
h2.ital { font-style: italic; }
.note { color: #e00; font-weight: bold; font-size: 12pt; margin: 4pt 0; text-align: left; }
.todo { background: #ffef9e; font-weight: bold; }
h3 { font-size: 11pt; margin: 9pt 0 3pt; }
p, li { margin: 3pt 0; text-align: justify; }
ul, ol { margin: 2pt 0 2pt 16pt; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 5pt 0; font-size: 8.3pt; }
tr { page-break-inside: avoid; }
h2, h3 { break-after: avoid; page-break-after: avoid; }
th, td { border: 1px solid #888; padding: 2pt 4pt; vertical-align: top; text-align: left; }
th { background: #eee; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.4pt; }
pre { background: #f6f6f6; border: 1px solid #ccc; padding: 4pt 6pt; font-size: 7.2pt; line-height: 1.25;
      white-space: pre-wrap; word-break: break-word; margin: 4pt 0; }
pre code { font-size: 7.2pt; }
pre.mermaid { background: none; border: none; text-align: center; font-size: 10pt; page-break-inside: avoid; }
pre.mermaid svg { max-height: 105mm; }
figure { margin: 6pt 0; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; max-height: 65mm; border: 1px solid #999; }
figcaption { font-size: 8.6pt; font-style: italic; margin-top: 2pt; }
.pending { border: 2px dashed #b00; color: #b00; padding: 10pt; font-size: 9pt; text-align: center; margin: 6pt 0; }
.pb { page-break-after: always; }
.cover { text-align: center; padding: 22mm 4mm 0 16mm; position: relative; height: 234mm; overflow: hidden; }
.cover .bar { position: absolute; left: 0; top: 14mm; width: 8mm; height: 242mm; background: #b71f31;
  border-right: 3mm solid #ed1c24; }
.cover .logo { width: 62mm; display: block; margin: 0 auto 16mm; }
.cover .task { font-size: 14pt; margin-bottom: 16mm; }
.cover .topic { font-size: 19pt; font-weight: bold; margin: 0 10mm 14mm; text-align: center; }
.cover .by { font-size: 11pt; margin: 6mm 0; text-align: center; }
.cover .names { font-size: 15pt; line-height: 1.6; margin-bottom: 10mm; text-align: center; }
.cover .names .rn { font-size: 11pt; }
.cover .subject { font-size: 20pt; font-weight: bold; margin-bottom: 22mm; text-align: center; }
.cover .dept { font-size: 12pt; font-weight: bold; text-align: center; }
"""


def build_html(md_text: str) -> str:
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"], output_format="html5")
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<pre class="mermaid">{html.unescape(m.group(1))}</pre>', body, flags=re.S)

    def figure(m):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(0)))
        src, alt = attrs.get("src", ""), html.unescape(attrs.get("alt", ""))
        if os.path.isfile(os.path.join(DOCS, src)):
            return f'<figure><img src="{src}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>'
        return f'<div class="pending">SCREENSHOT PENDING — {html.escape(alt)}<br>(expected file: docs/{html.escape(src)})</div>'
    body = re.sub(r"<p>\s*(<img [^>]*>)\s*</p>", lambda m: figure(re.match(r".*", m.group(1))), body)
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Nidaan IA-II Report</title>"
            f"<style>{CSS}</style>"
            "<script src='https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js'></script></head><body>"
            f"{body}<script>mermaid.initialize({{startOnLoad:true, theme:'neutral', "
            "flowchart:{useMaxWidth:true}, sequence:{useMaxWidth:true}}});</script></body></html>")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=CHROME)
    a = ap.parse_args()
    with open(SRC, encoding="utf-8") as f:
        page = build_html(f.read())
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    subprocess.run([a.chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=20000", f"--print-to-pdf={OUT_PDF}", "file://" + OUT_HTML],
                   check=True, capture_output=True)
    try:
        from pypdf import PdfReader
        print(f"{OUT_PDF}: {len(PdfReader(OUT_PDF).pages)} pages")
    except ImportError:
        print(f"{OUT_PDF} written (install pypdf to print the page count)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
