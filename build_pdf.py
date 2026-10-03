# -*- coding: utf-8 -*-
"""
build_pdf.py - turn PDQ_BASICS.md and HOW_TO_RUN.md into PDFs, in the Trace report style.

    python build_pdf.py

You only need this if you edit PDQ_BASICS.md or HOW_TO_RUN.md and want a fresh PDF. It uses the same
renderer as the onboarding packs (onboarding/week*/build_week*_pdfs.py), so the PDFs
look the same. It needs the packages reportlab and pillow:

    pip install reportlab pillow
"""
from __future__ import annotations
import io
import re
import sys
import textwrap
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
LOGO = HERE / "trace_logo.png"          # a copy of the Trace logo, kept next to this script

# ---- the look: same colours and sizes as the onboarding packs -------------------------
BLUE = colors.HexColor("#1565C0"); DARK = colors.HexColor("#1F1F1F")
MUTED = colors.HexColor("#6B6B6B"); ACCENT = colors.HexColor("#003775")
s = getSampleStyleSheet()
TITLE = ParagraphStyle("t", parent=s["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=BLUE, spaceAfter=6)
SUB = ParagraphStyle("su", parent=s["BodyText"], fontName="Helvetica-Oblique", fontSize=10.5, leading=15, textColor=MUTED, spaceAfter=14)
H1 = ParagraphStyle("h1", parent=s["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=BLUE, spaceBefore=18, spaceAfter=8)
H2 = ParagraphStyle("h2", parent=s["Heading3"], fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=ACCENT, spaceBefore=12, spaceAfter=6)
BODY = ParagraphStyle("b", parent=s["BodyText"], fontName="Helvetica", fontSize=10, leading=15.5, textColor=DARK, spaceAfter=9)
BULL = ParagraphStyle("bu", parent=BODY, leftIndent=14, bulletIndent=4, spaceAfter=5)
QUOTE = ParagraphStyle("q", parent=BODY, leftIndent=16, textColor=DARK, spaceAfter=7)
CODE = ParagraphStyle("cd", fontName="Courier", fontSize=8.2, leading=11, textColor=DARK,
                      backColor=colors.HexColor("#F4F6FA"), borderColor=colors.HexColor("#C9D6E5"),
                      borderWidth=0.75, borderPadding=8, spaceBefore=4, spaceAfter=10)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.7, leading=11.5, spaceAfter=0)
WM = ParagraphStyle("wm", parent=BODY, fontName="Helvetica-Bold", fontSize=13, textColor=ACCENT, alignment=2)
WML = ParagraphStyle("wml", parent=BODY, fontName="Helvetica-Oblique", fontSize=8.5, textColor=MUTED, alignment=2)


def inline(t: str) -> str:
    """Turn the little bits of markdown inside a line (bold, italic, code) into PDF markup."""
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+?)`", r"<font face='Courier' size='8.6'>\1</font>", t)
    return t


def P(t, st):
    return Paragraph(inline(t), st)


def cellp(t, bold=False, white=False):
    st = ParagraphStyle("c", parent=CELL, textColor=(colors.white if white else DARK),
                        fontName=("Helvetica-Bold" if bold else "Helvetica"))
    return Paragraph(inline(t), st)


def header(right_label):
    """The strip at the top of page one: the logo on the left, the title on the right."""
    cells = []
    if LOGO.is_file():
        from PIL import Image as PILImage
        pw, ph = PILImage.open(str(LOGO)).size
        cells.append(Image(str(LOGO), width=2.1 * cm, height=2.1 * cm * ph / pw))
    else:
        cells.append(Paragraph("Trace", TITLE))
    cells.append([Paragraph("Trace Onboarding", WML), Paragraph(right_label, WM)])
    h = Table([cells], colWidths=[9 * cm, 8 * cm])
    h.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return h


def md_table(lines):
    """A markdown table (lines starting with |) becomes a PDF table with a coloured header row."""
    rows = []
    for ln in lines:
        if re.match(r"^\|\s*-", ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return None
    ncol = max(len(r) for r in rows)
    data = [[cellp(c, bold=(i == 0), white=(i == 0)) for c in (r + [""] * (ncol - len(r)))] for i, r in enumerate(rows)]
    widths = [17.0 * cm / ncol] * ncol
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D6E5")),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FC")]),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return t


def md_to_flowables(md: str, right_label: str):
    """Walk the markdown line by line and build the list of things to draw."""
    E = [header(right_label), Spacer(1, 0.5 * cm)]
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            # Courier at 8.2 pt fits about 96 characters across the page; longer printout
            # lines are wrapped with an indent so nothing runs off the right edge
            wrapped = []
            for ln in block:
                wrapped += textwrap.wrap(ln, width=96, subsequent_indent="      ", break_long_words=True,
                                         break_on_hyphens=False, drop_whitespace=False) or [""]
            E.append(Preformatted("\n".join(wrapped), CODE)); i += 1; continue
        if ln.startswith("|"):
            tbl = [ln]
            while i + 1 < len(lines) and lines[i + 1].startswith("|"):
                i += 1; tbl.append(lines[i])
            t = md_table(tbl)
            if t is not None:
                E.append(t); E.append(Spacer(1, 0.25 * cm))
            i += 1; continue
        st = ln.strip()
        if ln.startswith("# "):
            E.append(P(ln[2:], TITLE))
        elif ln.startswith("## "):
            E.append(P(ln[3:], H1))
        elif ln.startswith("### "):
            E.append(P(ln[4:], H2))
        elif st.startswith("*") and st.endswith("*") and not st.startswith("**") and len(st) > 40:
            E.append(P(st.strip("*"), SUB))          # the italic line under the title
        elif st == "---":
            E.append(Spacer(1, 0.2 * cm))
        elif re.match(r"^\d+\.\s", st):
            E.append(Paragraph(inline(st), BULL))
        elif st.startswith("- "):
            E.append(Paragraph("•  " + inline(st[2:]), BULL))
        elif st.startswith(">"):
            # "> " lines are the spoken parts of a meeting script. Consecutive lines join
            # into one paragraph; a bare ">" line is a pause between paragraphs.
            para = [st.lstrip(">").strip()]
            while i + 1 < len(lines) and lines[i + 1].strip().startswith(">"):
                i += 1
                nxt = lines[i].strip().lstrip(">").strip()
                if nxt:
                    para.append(nxt)
                elif para:
                    E.append(P(" ".join(para), QUOTE)); para = []
            if para:
                E.append(P(" ".join(para), QUOTE))
        elif st.startswith("!["):
            # ![caption](path/to/image.png) - a screenshot, scaled to the text width
            m = re.match(r"^!\[[^\]]*\]\(([^)]+)\)$", st)
            img_path = HERE / m.group(1) if m else None
            if img_path is not None and img_path.is_file():
                from PIL import Image as PILImage
                pw, ph = PILImage.open(str(img_path)).size
                w = min(15.5 * cm, pw * 0.65)       # never blow a small shot up past readable
                E.append(Image(str(img_path), width=w, height=w * ph / pw))
                E.append(Spacer(1, 0.3 * cm))
        elif st:
            para = [st]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||-|\d+\.|```|\*|---)", lines[i + 1].strip()):
                i += 1; para.append(lines[i].strip())
            E.append(P(" ".join(para), BODY))
        i += 1
    return E


def footer(canv, doc):
    canv.saveState(); canv.setFont("Helvetica", 8); canv.setFillColor(MUTED)
    canv.drawString(2 * cm, 1.2 * cm, "Trace internal. Prepared for Nada. September 2026.")
    canv.drawRightString(19 * cm, 1.2 * cm, f"Page {canv.getPageNumber()}"); canv.restoreState()


JOBS = [("PDQ_BASICS.md", "PDQ_BASICS.pdf", "PDQ · THE BASICS"),
        ("HOW_TO_RUN.md", "HOW_TO_RUN.pdf", "HOW TO RUN IT")]

if __name__ == "__main__":
    for src, out, label in JOBS:
        md = (HERE / src).read_text(encoding="utf-8")
        doc = SimpleDocTemplate(str(HERE / out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                                topMargin=1.6 * cm, bottomMargin=2 * cm)
        doc.build(md_to_flowables(md, label), onFirstPage=footer, onLaterPages=footer)
        print("saved", HERE / out)
