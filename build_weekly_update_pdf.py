from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, SimpleDocTemplate, Table

from build_pdf import footer, md_to_flowables


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "PDQ_WEEKLY_UPDATE_19_SEPTEMBER_2026.md"
OUTPUT = HERE / "output" / "pdf" / "PDQ_WEEKLY_UPDATE_19_SEPTEMBER_2026.pdf"


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    markdown = SOURCE.read_text(encoding="utf-8")
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.6 * cm,
        bottomMargin=2 * cm,
        title="Fixing the PDQ false positive",
        author="Nada",
        subject="PDQ weekly findings - 19 September 2026",
    )
    flowables = md_to_flowables(markdown, "PDQ - WEEKLY FINDINGS")
    # The report uses small comparison tables. Keep each one on a single page
    # so a trailing row never appears by itself after a page break.
    flowables = [KeepTogether([item]) if isinstance(item, Table) else item for item in flowables]
    doc.build(
        flowables,
        onFirstPage=footer,
        onLaterPages=footer,
    )
    return OUTPUT


if __name__ == "__main__":
    print(build())
