"""
Export Module (`exporter.py`)
=============================
Generates ATS-friendly PDF and DOCX documents from structured resume data.

ATS BEST PRACTICES COMPLIANCE:
1. Single column, top-to-bottom logical reading order.
2. Standard section headings (SUMMARY, EXPERIENCE, EDUCATION, SKILLS, PROJECTS, CERTIFICATIONS).
3. No tables, multi-column text frames, images, or graphics in the body content.
4. Clean typography (standard fonts Helvetica/Arial/Calibri), standard 0.75-inch margins.
5. Standard bullet points and explicit role header hierarchies (Title, Employer, Dates, Location).
6. Robust error handling for export failures.
"""
import io
import logging
from typing import Optional

import docx
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from ..schemas import StructuredResume

logger = logging.getLogger(__name__)


class ExportError(Exception):
    """Raised when PDF or DOCX document generation fails."""

    def __init__(self, message: str, format_type: str = "pdf"):
        super().__init__(message)
        self.message = message
        self.format_type = format_type


def generate_docx_resume(resume: StructuredResume) -> bytes:
    """
    Generates an ATS-compliant Word document (.docx):
    - Single column
    - Standard headings
    - No tables or drawing shapes
    - Standard margins and bullet lists
    """
    try:
        doc = Document()

        # Set 0.75 in (54 pt) margins for standard ATS readability
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.75)
            section.bottom_margin = Inches(0.75)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)

        # Base Normal style
        normal_style = doc.styles["Normal"]
        normal_style.font.name = "Calibri"
        normal_style.font.size = Pt(10.5)
        normal_style.font.color.rgb = RGBColor(33, 37, 41)
        normal_style.paragraph_format.line_spacing = 1.15
        normal_style.paragraph_format.space_after = Pt(2)

        # 1. Header (Name + Contact details)
        name = resume.contact.name or "Candidate Name"
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(2)
        title_run = title_p.add_run(name)
        title_run.font.size = Pt(20)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(15, 23, 42)

        contact_parts = []
        if resume.contact.email:
            contact_parts.append(resume.contact.email)
        if resume.contact.phone:
            contact_parts.append(resume.contact.phone)
        if resume.contact.location:
            contact_parts.append(resume.contact.location)
        if resume.contact.linkedin:
            contact_parts.append(resume.contact.linkedin)
        if resume.contact.website:
            contact_parts.append(resume.contact.website)

        if contact_parts:
            contact_p = doc.add_paragraph()
            contact_p.paragraph_format.space_after = Pt(8)
            contact_run = contact_p.add_run(" | ".join(contact_parts))
            contact_run.font.size = Pt(9.5)
            contact_run.font.color.rgb = RGBColor(71, 85, 105)

        def add_section_header(title: str):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(title.upper())
            run.font.size = Pt(12)
            run.font.bold = True
            run.font.color.rgb = RGBColor(30, 41, 59)

        # 2. Summary
        if resume.summary:
            add_section_header("Professional Summary")
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            p.add_run(resume.summary)

        # 3. Skills
        if resume.skills:
            add_section_header("Core Skills")
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            p.add_run(", ".join(resume.skills))

        # 4. Work Experience
        if resume.experience:
            add_section_header("Work Experience")
            for exp in resume.experience:
                # Role Header: Title at Company | Dates | Location
                role_p = doc.add_paragraph()
                role_p.paragraph_format.space_before = Pt(6)
                role_p.paragraph_format.space_after = Pt(2)
                role_p.paragraph_format.keep_with_next = True

                title_run = role_p.add_run(exp.title)
                title_run.font.bold = True
                title_run.font.size = Pt(11)

                if exp.company:
                    comp_run = role_p.add_run(f" | {exp.company}")
                    comp_run.font.bold = True

                meta_parts = []
                if exp.dates:
                    meta_parts.append(exp.dates)
                if exp.location:
                    meta_parts.append(exp.location)
                if meta_parts:
                    meta_run = role_p.add_run(f" ({' | '.join(meta_parts)})")
                    meta_run.font.color.rgb = RGBColor(100, 116, 139)

                # Bullets
                for bullet in exp.bullets:
                    bp = doc.add_paragraph(style="List Bullet")
                    bp.paragraph_format.space_after = Pt(2)
                    bp.paragraph_format.line_spacing = 1.15
                    bp.add_run(bullet)

        # 5. Education
        if resume.education:
            add_section_header("Education")
            for edu in resume.education:
                edu_p = doc.add_paragraph()
                edu_p.paragraph_format.space_before = Pt(4)
                edu_p.paragraph_format.space_after = Pt(1)
                edu_p.paragraph_format.keep_with_next = True

                deg_run = edu_p.add_run(edu.degree)
                deg_run.font.bold = True

                if edu.institution:
                    inst_run = edu_p.add_run(f" | {edu.institution}")
                    inst_run.font.bold = True

                if edu.dates:
                    dates_run = edu_p.add_run(f" ({edu.dates})")
                    dates_run.font.color.rgb = RGBColor(100, 116, 139)

                for detail in edu.details:
                    dp = doc.add_paragraph(style="List Bullet")
                    dp.paragraph_format.space_after = Pt(1)
                    dp.add_run(detail)

        # 6. Projects
        if resume.projects:
            add_section_header("Projects")
            for proj in resume.projects:
                proj_p = doc.add_paragraph()
                proj_p.paragraph_format.space_before = Pt(4)
                proj_p.paragraph_format.space_after = Pt(1)
                proj_p.paragraph_format.keep_with_next = True

                p_run = proj_p.add_run(proj.name)
                p_run.font.bold = True

                if proj.description:
                    d_run = proj_p.add_run(f" | {proj.description}")
                    d_run.font.italic = True

                for pb in proj.bullets:
                    pbp = doc.add_paragraph(style="List Bullet")
                    pbp.paragraph_format.space_after = Pt(1)
                    pbp.add_run(pb)

        # 7. Certifications
        if resume.certifications:
            add_section_header("Certifications")
            for cert in resume.certifications:
                cp = doc.add_paragraph(style="List Bullet")
                cp.paragraph_format.space_after = Pt(1)
                cp.add_run(cert)

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf.getvalue()
    except Exception as exc:
        logger.error("Failed to generate DOCX resume: %s", exc, exc_info=True)
        raise ExportError(
            f"Failed to generate Word (.docx) document: {str(exc)}", format_type="docx"
        ) from exc


def generate_pdf_resume(resume: StructuredResume) -> bytes:
    """
    Generates an ATS-compliant PDF document using ReportLab:
    - Flowable paragraphs in logical single-column order
    - No multi-column layout frames or graphic decorations
    - Standard section headings with clean rule separators
    - Escaped XML tags for ReportLab safety
    """
    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            leftMargin=45,
            rightMargin=45,
            topMargin=45,
            bottomMargin=45,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ATS_Name",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=3,
        )

        contact_style = ParagraphStyle(
            "ATS_Contact",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
            spaceAfter=8,
        )

        heading_style = ParagraphStyle(
            "ATS_Heading",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=8,
            spaceAfter=3,
            keepWithNext=True,
        )

        body_style = ParagraphStyle(
            "ATS_Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=4,
        )

        role_header_style = ParagraphStyle(
            "ATS_RoleHeader",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=5,
            spaceAfter=2,
            keepWithNext=True,
        )

        bullet_style = ParagraphStyle(
            "ATS_Bullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#334155"),
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=2.5,
        )

        story = []

        def clean_xml(txt: str) -> str:
            """Escapes ReportLab XML control characters & and < >."""
            if not txt:
                return ""
            return (
                str(txt)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        # 1. Name & Contact
        name = clean_xml(resume.contact.name or "Candidate Name")
        story.append(Paragraph(name, title_style))

        contact_parts = []
        if resume.contact.email:
            contact_parts.append(clean_xml(resume.contact.email))
        if resume.contact.phone:
            contact_parts.append(clean_xml(resume.contact.phone))
        if resume.contact.location:
            contact_parts.append(clean_xml(resume.contact.location))
        if resume.contact.linkedin:
            contact_parts.append(clean_xml(resume.contact.linkedin))
        if resume.contact.website:
            contact_parts.append(clean_xml(resume.contact.website))

        if contact_parts:
            story.append(Paragraph(" | ".join(contact_parts), contact_style))

        def add_heading(title: str):
            story.append(Spacer(1, 4))
            story.append(Paragraph(clean_xml(title.upper()), heading_style))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=colors.HexColor("#cbd5e1"),
                    spaceBefore=1,
                    spaceAfter=4,
                )
            )

        # 2. Professional Summary
        if resume.summary:
            add_heading("Professional Summary")
            story.append(Paragraph(clean_xml(resume.summary), body_style))

        # 3. Core Skills
        if resume.skills:
            add_heading("Core Skills")
            story.append(Paragraph(clean_xml(", ".join(resume.skills)), body_style))

        # 4. Work Experience
        if resume.experience:
            add_heading("Work Experience")
            for exp in resume.experience:
                header_parts = [f"<b>{clean_xml(exp.title)}</b>"]
                if exp.company:
                    header_parts.append(f"<b>{clean_xml(exp.company)}</b>")
                meta = []
                if exp.dates:
                    meta.append(clean_xml(exp.dates))
                if exp.location:
                    meta.append(clean_xml(exp.location))
                if meta:
                    header_parts.append(f"<font color='#64748b'>({' | '.join(meta)})</font>")

                story.append(Paragraph(" | ".join(header_parts), role_header_style))

                for bullet in exp.bullets:
                    bullet_html = f"&bull;&nbsp; {clean_xml(bullet)}"
                    story.append(Paragraph(bullet_html, bullet_style))

        # 5. Education
        if resume.education:
            add_heading("Education")
            for edu in resume.education:
                edu_parts = [f"<b>{clean_xml(edu.degree)}</b>"]
                if edu.institution:
                    edu_parts.append(f"<b>{clean_xml(edu.institution)}</b>")
                if edu.dates:
                    edu_parts.append(f"<font color='#64748b'>({clean_xml(edu.dates)})</font>")

                story.append(Paragraph(" | ".join(edu_parts), role_header_style))
                for det in edu.details:
                    story.append(Paragraph(f"&bull;&nbsp; {clean_xml(det)}", bullet_style))

        # 6. Projects
        if resume.projects:
            add_heading("Projects")
            for proj in resume.projects:
                p_parts = [f"<b>{clean_xml(proj.name)}</b>"]
                if proj.description:
                    p_parts.append(f"<i>{clean_xml(proj.description)}</i>")
                story.append(Paragraph(" | ".join(p_parts), role_header_style))
                for pb in proj.bullets:
                    story.append(Paragraph(f"&bull;&nbsp; {clean_xml(pb)}", bullet_style))

        # 7. Certifications
        if resume.certifications:
            add_heading("Certifications")
            for cert in resume.certifications:
                story.append(Paragraph(f"&bull;&nbsp; {clean_xml(cert)}", bullet_style))

        doc.build(story)
        buf.seek(0)
        return buf.getvalue()
    except Exception as exc:
        logger.error("Failed to generate PDF resume: %s", exc, exc_info=True)
        raise ExportError(
            f"Failed to generate ATS PDF document: {str(exc)}", format_type="pdf"
        ) from exc
