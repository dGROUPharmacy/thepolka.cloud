"""
renderer/pdf.py
Renders the resume to PDF bytes using WeasyPrint.
WeasyPrint converts the HTML renderer output directly — no layout duplication.

Install: pip install weasyprint
Linux deps: apt install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0
"""

from .html import render_html


def render_pdf(data: dict) -> bytes:
    """
    Returns PDF as bytes by running WeasyPrint on the HTML output.
    """
    try:
        from weasyprint import HTML as WP_HTML
        html_string = render_html(data)
        pdf_bytes = WP_HTML(string=html_string).write_pdf()
        return pdf_bytes

    except ImportError:
        # Fallback: return a helpful placeholder PDF using reportlab
        return _fallback_pdf(data)


def _fallback_pdf(data: dict) -> bytes:
    """
    Minimal fallback using reportlab if WeasyPrint is not installed.
    Produces a basic but readable PDF.
    """
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_LEFT
        import io

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=LETTER,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
        )

        styles = getSampleStyleSheet()
        name_style = ParagraphStyle("Name", fontSize=20, fontName="Helvetica-Bold", spaceAfter=4)
        title_style = ParagraphStyle("Title", fontSize=12, fontName="Helvetica-Oblique", spaceAfter=4, textColor=colors.HexColor("#555555"))
        purpose_style = ParagraphStyle("Purpose", fontSize=11, spaceAfter=6, leading=16)
        contact_style = ParagraphStyle("Contact", fontSize=10, textColor=colors.HexColor("#555555"), spaceAfter=12)
        section_style = ParagraphStyle("Section", fontSize=9, fontName="Helvetica-Bold", textColor=colors.HexColor("#888888"), spaceAfter=4, spaceBefore=14, letterSpacing=1.5)
        entry_title_style = ParagraphStyle("EntryTitle", fontSize=12, fontName="Helvetica-Bold", spaceAfter=2)
        ari_style = ParagraphStyle("ARI", fontSize=10, leading=16, leftIndent=12, spaceAfter=1)

        story = []

        story.append(Paragraph(data["name"] or "Resume", name_style))
        if data["title"]:
            story.append(Paragraph(data["title"], title_style))
        if data["purpose"]:
            story.append(Paragraph(data["purpose"], purpose_style))

        contact_parts = []
        if data["email"]:    contact_parts.append(data["email"])
        if data["phone"]:    contact_parts.append(data["phone"])
        if data["location"]: contact_parts.append(data["location"])
        for lnk in data["links"]:
            contact_parts.append(f"{lnk['title']}: {lnk['url']}")
        if contact_parts:
            story.append(Paragraph("  ·  ".join(contact_parts), contact_style))

        story.append(HRFlowable(width="100%", thickness=1, color=colors.black))

        def ari_section(entries, heading):
            if not entries:
                return
            story.append(Paragraph(heading.upper(), section_style))
            for e in entries:
                story.append(Paragraph(f"<b>{e['title']}</b>", entry_title_style))
                if e["action"]: story.append(Paragraph(f"<b>Action</b>  {e['action']}", ari_style))
                if e["result"]: story.append(Paragraph(f"<b>Result</b>  {e['result']}", ari_style))
                if e["impact"]: story.append(Paragraph(f"<b>Impact</b>  {e['impact']}", ari_style))
                story.append(Spacer(1, 6))

        ari_section(data["experience"],   "Experience")
        ari_section(data["volunteer"],    "Volunteer Work")
        ari_section(data["certificates"], "Certificates")
        ari_section(data["awards"],       "Awards")

        if data["hobbies"]:
            story.append(Paragraph("HOBBIES & INTERESTS", section_style))
            story.append(Paragraph(" · ".join(data["hobbies"]), ari_style))

        doc.build(story)
        buf.seek(0)
        return buf.read()

    except ImportError:
        return b"%PDF-1.4 placeholder - install weasyprint or reportlab"

