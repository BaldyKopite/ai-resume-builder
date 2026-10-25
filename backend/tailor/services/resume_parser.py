"""
Resume Parser (`resume_parser.py`)
==================================
Extracts structured resume data (contact details, summary, experience, education,
skills, certifications, projects) from PDF files, DOCX files, or pasted plain text.
Includes explicit error handling for unreadable/corrupted files and detects
sparse or missing sections so the user is clearly guided on what information is needed.
"""
import io
import re
from typing import Dict, List, Optional, Tuple

import docx
from pypdf import PdfReader

from ..schemas import (
    ContactDetails,
    EducationItem,
    ExperienceItem,
    ProjectItem,
    StructuredResume,
)


class ResumeParseError(Exception):
    """Raised when an uploaded resume file is unsupported, corrupted, encrypted, or unreadable."""

    def __init__(self, message: str, code: str = "RESUME_UNREADABLE"):
        super().__init__(message)
        self.message = message
        self.code = code


SECTION_HEADINGS_MAP: Dict[str, List[str]] = {
    "summary": [
        "professional summary",
        "executive summary",
        "summary",
        "profile",
        "professional profile",
        "career objective",
        "objective",
        "about me",
    ],
    "experience": [
        "work experience",
        "professional experience",
        "experience",
        "employment history",
        "work history",
        "career history",
        "relevant experience",
    ],
    "education": [
        "education",
        "academic background",
        "education & training",
        "education and training",
        "academic qualifications",
    ],
    "skills": [
        "technical skills",
        "core competencies",
        "skills & expertise",
        "skills and tools",
        "skills",
        "technologies",
        "key skills",
        "areas of expertise",
    ],
    "certifications": [
        "certifications",
        "licenses & certifications",
        "licenses and certifications",
        "certificates",
        "autonomous and mining systems training",
        "mining systems training",
        "licences",
        "licenses",
        "training & certifications",
        "professional certifications",
        "credentials",
    ],
    "projects": [
        "projects",
        "key projects",
        "selected projects",
        "personal projects",
        "technical projects",
        "open source & projects",
    ],
}

DATE_RANGE_REGEX = re.compile(
    r"(?P<dates>"
    r"(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{4}|\b(?:19|20)\d{2}\b|\b\d{1,2}/(?:19|20)\d{2}\b)"
    r"\s*(?:[-–—]|to)\s*"
    r"(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{4}|\b(?:19|20)\d{2}\b|\b\d{1,2}/(?:19|20)\d{2}\b|Present|Current|Now)"
    r")",
    re.IGNORECASE,
)

SINGLE_YEAR_REGEX = re.compile(
    r"\b(?:Class of\s+|Graduated\s+)?((?:19|20)\d{2})\b", re.IGNORECASE
)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts raw text from a PDF file stream. Raises ResumeParseError if corrupted or unreadable."""
    if not file_bytes or len(file_bytes) < 10:
        raise ResumeParseError("The uploaded PDF file is empty.", code="EMPTY_PDF_FILE")

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ResumeParseError(
                    "The uploaded PDF is password-protected. Please upload an unencrypted PDF, DOCX, or paste your resume text.",
                    code="ENCRYPTED_PDF",
                ) from exc

        pages_text: List[str] = []
        for page in reader.pages:
            page_txt = page.extract_text() or ""
            if page_txt.strip():
                pages_text.append(page_txt)

        combined = "\n".join(pages_text).strip()
        return combined
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError(
            "Unable to read the uploaded PDF file. The file appears corrupted or invalid. Please upload a valid PDF/DOCX or paste your resume text.",
            code="CORRUPTED_PDF_FILE",
        ) from exc


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extracts raw text from a DOCX file stream, including paragraphs and any table cells."""
    if not file_bytes or len(file_bytes) < 10:
        raise ResumeParseError("The uploaded DOCX file is empty.", code="EMPTY_DOCX_FILE")

    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        lines: List[str] = []
        for para in doc.paragraphs:
            txt = (para.text or "").strip()
            if txt:
                # Preserve bullet list style if paragraph style is List Bullet
                style_name = (para.style.name if para.style else "").lower()
                if "bullet" in style_name or "list" in style_name:
                    if not re.match(r"^[\•\-\*▪▸‣◦·]", txt):
                        txt = f"- {txt}"
                lines.append(txt)

        # Also extract text from tables in case user's original resume used layout tables
        for table in doc.tables:
            for row in table.rows:
                row_cells = []
                for cell in row.cells:
                    cell_text = (cell.text or "").strip()
                    if cell_text and cell_text not in row_cells:
                        row_cells.append(cell_text)
                if row_cells:
                    lines.append(" | ".join(row_cells))

        return "\n".join(lines).strip()
    except Exception as exc:
        raise ResumeParseError(
            "Unable to read the uploaded DOCX file. The file appears corrupted or is not a valid Word document. Please upload a valid DOCX/PDF or paste your resume text.",
            code="CORRUPTED_DOCX_FILE",
        ) from exc


def extract_text_from_upload(filename: str, file_bytes: bytes) -> str:
    """Routes file extraction based on file extension."""
    lower_name = (filename or "").lower().strip()
    if lower_name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if lower_name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    if lower_name.endswith(".txt") or lower_name.endswith(".md"):
        try:
            return file_bytes.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            raise ResumeParseError(
                "Could not decode text file.", code="CORRUPTED_TEXT_FILE"
            ) from exc

    raise ResumeParseError(
        f"Unsupported file format '{filename}'. Please upload a PDF (.pdf) or Word (.docx) file, or paste your resume text.",
        code="UNSUPPORTED_FILE_FORMAT",
    )


def _match_section_heading(line: str) -> Optional[str]:
    """Checks if a line is a standard resume section heading."""
    cleaned = re.sub(r"^[\s#\*\_\-–—:•]+|[\s#\*\_\-–—:•]+$", "", line).strip().lower()
    if not cleaned or len(cleaned) > 45:
        return None
    for section_key, aliases in SECTION_HEADINGS_MAP.items():
        if cleaned in aliases:
            return section_key
    return None


def _parse_contact_header(header_lines: List[str], full_text: str) -> ContactDetails:
    """Extracts contact details (name, email, phone, location, LinkedIn, website) strictly from the resume."""
    joined_header = "\n".join(header_lines) if header_lines else full_text[:600]

    # Email
    email_match = re.search(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
        joined_header or full_text,
    )
    email = email_match.group(0) if email_match else ""

    # Phone
    phone_match = re.search(
        r"(?:\+?\d{1,3}[\s\-\.]?)?(?:\(\d{2,4}\)[\s\-\.]?|\d{2,4}[\s\-\.])\d{3,4}[\s\-\.]\d{3,4}",
        joined_header or full_text[:800],
    )
    phone = phone_match.group(0).strip() if phone_match else ""

    # LinkedIn
    linkedin_match = re.search(
        r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%/]+",
        joined_header or full_text,
        re.I,
    )
    linkedin = linkedin_match.group(0) if linkedin_match else ""

    # Website / GitHub / Portfolio
    website = ""
    for url_match in re.finditer(
        r"(?:https?://)?(?:www\.)?(?:github\.com/[A-Za-z0-9\-_]+|[A-Za-z0-9\-]+\.(?:dev|io|me|com|org|net)(?:/[A-Za-z0-9\-_%/]*)?)",
        joined_header,
        re.I,
    ):
        candidate_url = url_match.group(0)
        if "linkedin.com" in candidate_url.lower() or "@" in candidate_url:
            continue
        if any(
            mail_dom in candidate_url.lower()
            for mail_dom in ("gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com")
        ):
            continue
        website = candidate_url
        break

    # Name: usually the first non-empty line before any section header
    name = ""
    if header_lines:
        first_line = header_lines[0].strip()
        # If first line has pipe/bullet separators, take first segment
        first_segment = re.split(r"[\|•]", first_line)[0].strip()
        if (
            2 <= len(first_segment) <= 60
            and "@" not in first_segment
            and not re.search(r"\d{3}", first_segment)
        ):
            name = first_segment

    # Location: look for City, ST or City, Country pattern in header lines
    location = ""
    for line in header_lines:
        segments = [seg.strip() for seg in re.split(r"[\|•]", line) if seg.strip()]
        for seg in segments:
            if seg == name or seg == email or seg == phone or seg == linkedin or seg == website:
                continue
            if "@" in seg or "linkedin.com" in seg.lower() or "github.com" in seg.lower():
                continue
            if re.search(r"\d{3}[\s\-\.]\d{3}", seg):
                continue
            # Match "Location: City, State" or "City, State/Country"
            loc_clean = re.sub(r"^location\s*[:\-]\s*", "", seg, flags=re.I).strip()
            if (
                ("," in loc_clean or any(w in loc_clean.lower() for w in ("remote", "au", "usa", "uk", "ny", "ca", "tx", "wa", "nsw", "vic")))
                and 3 <= len(loc_clean) <= 55
            ):
                location = loc_clean
                break
        if location:
            break

    return ContactDetails(
        name=name,
        email=email,
        phone=phone,
        location=location,
        linkedin=linkedin,
        website=website,
    )


def _parse_experience_section(lines: List[str]) -> List[ExperienceItem]:
    """
    Parses experience section lines into structured ExperienceItem entries.
    Pre-processes and stitches broken/wrapped bullet lines so wrapped phrases
    (e.g. '...system upgrades, and' -> 'continuous improvement.') are not orphaned
    or misidentified as job titles.
    """
    # Step 1: Pre-stitch wrapped bullet lines
    stitched_lines: List[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        is_bullet = bool(re.match(r"^[\•\-\*▪▸‣◦·]|\d+[\.\)]", line))
        has_date = bool(DATE_RANGE_REGEX.search(line))

        if (
            stitched_lines
            and not is_bullet
            and not has_date
            and (
                stitched_lines[-1].rstrip().endswith(
                    ("and", ",", "in", "of", "with", "to", "for", "on", "and.", "&")
                )
                or line[0].islower()
            )
        ):
            stitched_lines[-1] = stitched_lines[-1].rstrip(". ") + " " + line
        else:
            stitched_lines.append(line)

    items: List[ExperienceItem] = []
    current_item: Optional[ExperienceItem] = None

    def flush_current():
        nonlocal current_item
        if current_item and (current_item.title or current_item.company or current_item.bullets):
            if not current_item.id:
                current_item.id = f"exp-{len(items) + 1}"
            items.append(current_item)
        current_item = None

    i = 0
    while i < len(stitched_lines):
        line = stitched_lines[i].strip()
        if not line:
            i += 1
            continue

        is_bullet = bool(re.match(r"^[\•\-\*▪▸‣◦·]|\d+[\.\)]", line))
        date_match = DATE_RANGE_REGEX.search(line)

        # Pattern A: Current line has Date range
        if not is_bullet and date_match:
            flush_current()
            dates_str = date_match.group("dates").strip()
            # Remainder of line without the date
            rem = (line[: date_match.start()] + " " + line[date_match.end() :]).strip(" |-–—,()•\t")

            # Check if next line is a job title / company (not a bullet, < 90 chars)
            next_line = stitched_lines[i + 1].strip() if i + 1 < len(stitched_lines) else ""
            next_is_bullet = bool(re.match(r"^[\•\-\*▪▸‣◦·]|\d+[\.\)]", next_line))

            if next_line and not next_is_bullet and len(next_line) < 95:
                # E.g. Line 1: '07/2022 – Present Perth, WA', Line 2: 'Machine Control and Guidance Technician, WesTrac CAT'
                title, company, loc_from_next = _split_role_and_company(next_line)
                location = rem or loc_from_next
                current_item = ExperienceItem(
                    id=f"exp-{len(items) + 1}",
                    title=title or next_line,
                    company=company or "",
                    location=location,
                    dates=dates_str,
                    bullets=[],
                )
                i += 2
                continue
            else:
                title, company, location = _split_role_and_company(rem)
                current_item = ExperienceItem(
                    id=f"exp-{len(items) + 1}",
                    title=title or "Role",
                    company=company or "",
                    location=location,
                    dates=dates_str,
                    bullets=[],
                )
                i += 1
                continue

        # Pattern B: Next line has Date range while current line is Title / Company
        if not is_bullet and i + 1 < len(stitched_lines):
            next_line = stitched_lines[i + 1].strip()
            next_date = DATE_RANGE_REGEX.search(next_line)
            if next_date and not re.match(r"^[\•\-\*▪▸‣◦·]", next_line) and len(next_line) < 65:
                flush_current()
                dates_str = next_date.group("dates").strip()
                title, company, location = _split_role_and_company(line)
                next_rem = (
                    next_line[: next_date.start()] + " " + next_line[next_date.end() :]
                ).strip(" |-–—,()•\t")
                if next_rem and not location:
                    location = next_rem
                elif next_rem and not company:
                    company = next_rem

                current_item = ExperienceItem(
                    id=f"exp-{len(items) + 1}",
                    title=title or line,
                    company=company or "",
                    location=location,
                    dates=dates_str,
                    bullets=[],
                )
                i += 2
                continue

        # Process bullet text or continuation
        bullet_txt = re.sub(r"^[\s•\-\*▪▸‣◦·]+", "", line).strip()
        if not bullet_txt:
            i += 1
            continue

        if current_item is not None:
            current_item.bullets.append(bullet_txt)
        else:
            current_item = ExperienceItem(
                id=f"exp-{len(items) + 1}",
                title="Professional Experience",
                company="",
                location="",
                dates="",
                bullets=[bullet_txt],
            )

        i += 1

    flush_current()
    return items


def _split_role_and_company(header_text: str) -> Tuple[str, str, str]:
    """Splits a role header string into (title, company, location)."""
    text = (header_text or "").strip(" |-–—,•")
    if not text:
        return "", "", ""

    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
        if len(parts) == 2:
            return parts[0], parts[1], ""
        return parts[0], "", ""

    if " at " in text:
        parts = text.split(" at ", 1)
        comp_loc = parts[1].strip()
        if "," in comp_loc:
            c_parts = [p.strip() for p in comp_loc.split(",", 1)]
            return parts[0].strip(), c_parts[0], c_parts[1]
        return parts[0].strip(), comp_loc, ""

    for sep in (" — ", " – ", " - "):
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            if len(parts) >= 3:
                return parts[0], parts[1], parts[2]
            if len(parts) == 2:
                return parts[0], parts[1], ""

    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) >= 3:
            return parts[0], parts[1], ", ".join(parts[2:])
        if len(parts) == 2:
            return parts[0], parts[1], ""

    return text, "", ""


def _parse_education_section(lines: List[str]) -> List[EducationItem]:
    """Parses education lines into EducationItem objects with multi-line wrap protection."""
    items: List[EducationItem] = []
    current: Optional[EducationItem] = None

    degree_keywords = (
        "bachelor",
        "master",
        "b.s",
        "b.a",
        "m.s",
        "m.a",
        "mba",
        "ph.d",
        "phd",
        "associate",
        "diploma",
        "degree",
        "b.eng",
        "b.comp",
        "b.sc",
        "m.sc",
        "trade qualification",
        "qualification",
        "apprenticeship",
        "apprentice",
        "certificate",
        "further education",
    )
    school_keywords = (
        "university",
        "college",
        "institute",
        "school",
        "academy",
        "polytechnic",
        "tafe",
    )

    # Pre-process lines to stitch multi-line degree titles wrapped across linebreaks (e.g. "Trade Qualification – Electronics &" + "Communications")
    stitched: List[str] = []
    skip_idx = False
    for i in range(len(lines)):
        if skip_idx:
            skip_idx = False
            continue
        line_cur = lines[i].strip()
        if not line_cur:
            continue
        # Check if next line is a continuation (ends with & or next line is not a bullet and < 40 chars)
        if i + 1 < len(lines):
            line_nxt = lines[i + 1].strip()
            if (line_cur.endswith(("&", "and", "/", "-")) or (len(line_cur) < 40 and any(k in line_cur.lower() for k in ("trade qualification", "bachelor", "master", "diploma")))) and not re.match(r"^[\•\-\*▪▸‣◦·]", line_nxt) and len(line_nxt) < 40:
                stitched.append(f"{line_cur.rstrip('& /-')} & {line_nxt.lstrip('& /-')}")
                skip_idx = True
                continue
        stitched.append(line_cur)

    for raw_line in stitched:
        line = raw_line.strip()
        if not line:
            continue
        is_bullet = bool(re.match(r"^[\•\-\*▪▸‣◦·]", line))
        clean = re.sub(r"^[\s•\-\*▪▸‣◦·]+", "", line).strip()

        date_match = DATE_RANGE_REGEX.search(clean) or SINGLE_YEAR_REGEX.search(clean)
        lower_clean = clean.lower()
        has_degree = any(k in lower_clean for k in degree_keywords)
        has_school = any(k in lower_clean for k in school_keywords)
        has_degree_or_school = has_degree or has_school

        # If current item lacks an institution and this line is an institution, assign it
        if current is not None and not current.institution and has_school and not has_degree:
            school_name, loc = clean, ""
            if "—" in clean or " - " in clean or "|" in clean:
                parts = re.split(r"\s*[—|\-]\s*", clean, maxsplit=1)
                school_name, loc = parts[0], parts[1]
            current.institution = school_name
            if loc and not current.dates:
                current.details.append(loc)
            continue

        if not is_bullet and (has_degree_or_school or current is None):
            if current:
                items.append(current)
            dates_str = ""
            if date_match:
                dates_str = date_match.group(0).strip()
                clean = (clean[: date_match.start()] + " " + clean[date_match.end() :]).strip(
                    " |-–—,()•"
                )

            degree, institution, _ = _split_role_and_company(clean)
            # If institution ended up in degree and degree in institution, swap if obvious
            if (
                degree
                and institution
                and any(k in degree.lower() for k in school_keywords)
                and any(k in institution.lower() for k in degree_keywords)
            ):
                degree, institution = institution, degree
            elif institution and not any(k in institution.lower() for k in school_keywords):
                # If the split part is a trade or study specialization (e.g. 'Trade Qualification - Electronics & Communications'),
                # treat the entire string as the degree and let the actual institution be found on the next line or details
                degree = clean
                institution = ""

            current = EducationItem(
                id=f"edu-{len(items) + 1}",
                degree=degree or clean,
                institution=institution,
                dates=dates_str,
                details=[],
            )
        else:
            if current is None:
                current = EducationItem(
                    id=f"edu-{len(items) + 1}",
                    degree=clean,
                    institution="",
                    dates="",
                    details=[],
                )
            else:
                current.details.append(clean)

    if current:
        items.append(current)
    return items


def _parse_skills_section(lines: List[str]) -> List[str]:
    """Parses skills section into clean individual skill tags, stripping noise and conjunctions."""
    skills: List[str] = []
    seen = set()
    for line in lines:
        clean = re.sub(r"^[\s•\-\*▪▸‣◦·]+", "", line).strip()
        if not clean:
            continue
        # Strip category prefix like "Languages: Python, TypeScript" -> "Python, TypeScript"
        if ":" in clean:
            prefix, rest = clean.split(":", 1)
            if len(prefix.strip()) <= 32:
                clean = rest.strip()
        tokens = re.split(r"[,;\|•]+", clean)
        for tok in tokens:
            # Strip leading conjunctions (e.g. "and DSS" -> "DSS", "& Telemetry" -> "Telemetry")
            s = re.sub(r"^(?:and|or|&)\s+", "", tok.strip(" ."), flags=re.I).strip(" .")
            if 1 < len(s) <= 45 and s.lower() not in seen:
                seen.add(s.lower())
                skills.append(s)
    return skills


def _parse_projects_section(lines: List[str]) -> List[ProjectItem]:
    """Parses projects section into ProjectItem objects."""
    projects: List[ProjectItem] = []
    current: Optional[ProjectItem] = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        is_bullet = bool(re.match(r"^[\•\-\*▪▸‣◦·]", line))
        clean = re.sub(r"^[\s•\-\*▪▸‣◦·]+", "", line).strip()

        if not is_bullet and (len(clean) < 90 or "|" in clean or " — " in clean or " - " in clean):
            if current:
                projects.append(current)
            name, desc, _ = _split_role_and_company(clean)
            current = ProjectItem(
                id=f"proj-{len(projects) + 1}",
                name=name or clean,
                description=desc,
                dates="",
                bullets=[],
            )
        else:
            if current is None:
                current = ProjectItem(
                    id=f"proj-{len(projects) + 1}",
                    name="Project",
                    description="",
                    dates="",
                    bullets=[clean],
                )
            else:
                current.bullets.append(clean)

    if current:
        projects.append(current)
    return projects


def parse_resume_text(raw_text: str) -> StructuredResume:
    """
    Parses raw resume text into a `StructuredResume` object and flags any
    missing or sparse sections so the user knows what information to add.
    """
    text = (raw_text or "").strip()
    if not text:
        return StructuredResume(
            missing_or_sparse_sections=[
                "Resume text is empty or could not be extracted. Please provide your contact info, work experience, education, and skills."
            ],
            raw_text="",
        )

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    header_lines: List[str] = []
    section_buckets: Dict[str, List[str]] = {
        "summary": [],
        "experience": [],
        "education": [],
        "skills": [],
        "certifications": [],
        "projects": [],
    }

    current_section: Optional[str] = None
    for line in lines:
        matched_heading = _match_section_heading(line)
        if matched_heading:
            current_section = matched_heading
            continue

        if current_section is None:
            header_lines.append(line)
        else:
            section_buckets[current_section].append(line)

    # If the resume had no standard headings at all, infer structure from content
    if all(len(v) == 0 for v in section_buckets.values()) and header_lines:
        contact_candidate_lines = header_lines[:3]
        body_lines = header_lines[3:] if len(header_lines) > 3 else header_lines[1:]
        header_lines = contact_candidate_lines
        section_buckets["experience"] = body_lines

    contact = _parse_contact_header(header_lines, text)

    # Check if header_lines after contact lines contain an unlabeled summary paragraph
    summary_lines = list(section_buckets["summary"])
    if not summary_lines and len(header_lines) > 2:
        for hline in header_lines[1:]:
            if (
                len(hline) > 65
                and "@" not in hline
                and "linkedin.com" not in hline.lower()
                and not re.search(r"\d{3}[\s\-\.]\d{3}", hline)
            ):
                summary_lines.append(hline)

    summary = " ".join(summary_lines).strip()
    experience = _parse_experience_section(section_buckets["experience"])
    education = _parse_education_section(section_buckets["education"])
    skills = _parse_skills_section(section_buckets["skills"])
    certifications = [
        re.sub(r"^[\s•\-\*▪▸‣◦·]+", "", c).strip()
        for c in section_buckets["certifications"]
        if c.strip()
    ]
    projects = _parse_projects_section(section_buckets["projects"])

    # Fallback skill detection from raw text if no explicit skills section was present
    if not skills:
        from .job_scraper import KNOWN_SKILLS_AND_KEYWORDS

        seen_sk = set()
        for kw in KNOWN_SKILLS_AND_KEYWORDS:
            pat = r"(?<![a-zA-Z0-9])" + re.escape(kw) + r"(?![a-zA-Z0-9])"
            if re.search(pat, text, re.I) and kw.lower() not in seen_sk:
                seen_sk.add(kw.lower())
                skills.append(kw)

    # Evaluate completeness and flag sparse or missing sections
    warnings: List[str] = []
    if not contact.name or not contact.email:
        warnings.append(
            "Contact Details: Name or email address could not be clearly detected. Please verify your contact header before exporting."
        )
    if not summary:
        warnings.append(
            "Professional Summary: No summary section was found in the original resume. A factual draft summary has been synthesized strictly from your existing roles and skills for your review."
        )
    if not experience:
        warnings.append(
            "Work Experience: No structured work experience entries were detected. Please add your roles, employers, dates, and achievement bullets."
        )
    else:
        total_bullets = sum(len(exp.bullets) for exp in experience)
        if total_bullets < 3:
            warnings.append(
                "Work Experience (Sparse): Very few achievement bullet points were found. Consider adding 3–5 concrete accomplishments per role."
            )
    if not education:
        warnings.append(
            "Education: No education section was found. Add your degree, institution, and graduation year if applicable."
        )
    if len(skills) < 3:
        warnings.append(
            "Skills: Fewer than 3 skills were detected. Consider listing your core technical and domain skills."
        )

    return StructuredResume(
        contact=contact,
        summary=summary,
        experience=experience,
        education=education,
        skills=skills,
        certifications=certifications,
        projects=projects,
        missing_or_sparse_sections=warnings,
        raw_text=text,
    )


def parse_resume(
    resume_file_name: Optional[str] = None,
    resume_file_bytes: Optional[bytes] = None,
    resume_text: Optional[str] = None,
) -> StructuredResume:
    """
    Main entry point for Deliverable 3:
    Accepts an uploaded file (PDF, DOCX) and/or pasted resume text.
    - If an uploaded file is unreadable/corrupted and no fallback text is given,
      raises `ResumeParseError` with a descriptive message.
    - If an uploaded PDF is a scanned image with near-zero extractable text,
      builds the best possible sparse structure (or uses `resume_text` if provided)
      and flags the missing sections clearly.
    """
    extracted_text = ""
    extra_warnings: List[str] = []

    if resume_file_bytes is not None and resume_file_name:
        try:
            extracted_text = extract_text_from_upload(resume_file_name, resume_file_bytes)
            if len(extracted_text.strip()) < 25:
                extra_warnings.append(
                    f"Uploaded file '{resume_file_name}' contained very little readable text (it may be a scanned image). Please review and complete all sections below."
                )
        except ResumeParseError:
            if resume_text and resume_text.strip():
                extracted_text = resume_text.strip()
                extra_warnings.append(
                    f"Uploaded file '{resume_file_name}' could not be read; fell back to pasted resume text."
                )
            else:
                raise

    if not extracted_text and resume_text and resume_text.strip():
        extracted_text = resume_text.strip()

    if not extracted_text and not extra_warnings:
        raise ResumeParseError(
            "No resume input provided. Please upload a PDF or DOCX resume file or paste your resume text.",
            code="MISSING_RESUME_INPUT",
        )

    structured = parse_resume_text(extracted_text)
    if extra_warnings:
        structured.missing_or_sparse_sections = (
            extra_warnings + structured.missing_or_sparse_sections
        )

    return structured
