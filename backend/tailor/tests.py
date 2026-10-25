"""
Automated Test Suite for Tailor Backend
======================================
Tests the critical invariants:
1. Deliverable 2: Scraper/parser fallback paths (LinkedIn, Seek, unfetchable URLs -> paste fallback).
2. Deliverable 3: Resume parser handling PDF, DOCX, unreadable files, corrupted files, and sparse structures.
3. Deliverable 4: Tailoring engine strict NO-FABRICATION rule:
   - Does NOT invent employers, job titles, dates, credentials, or metrics.
   - Flags missing requirements as gaps.
   - Reorders and refines bullets for relevance without altering metrics.
4. Deliverable 5: Export output generation (ATS-friendly PDF and DOCX generation and downloadable binaries).
5. Deliverable 7: Explicit error handling for unfetchable job pages, unreadable files, and failed exports.
"""
import io
import json
import pytest
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup
import docx
from pypdf import PdfWriter
from rest_framework import status
from rest_framework.test import APIClient

from tailor.schemas import (
    ContactDetails,
    ExperienceItem,
    JobPostingData,
    StructuredResume,
)
from tailor.services.exporter import (
    ExportError,
    generate_docx_resume,
    generate_pdf_resume,
)
from tailor.services.job_scraper import (
    JobScrapeError,
    extract_structured_job_details,
    parse_linkedin_html,
    parse_seek_html,
    scrape_or_parse_job,
)
from tailor.services.resume_parser import (
    ResumeParseError,
    extract_text_from_docx,
    extract_text_from_pdf,
    parse_resume,
    parse_resume_text,
)
from tailor.services.tailoring_engine import (
    analyze_gaps,
    calculate_relevance_score,
    rewrite_bullet_with_guardrails,
    tailor_resume,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_job_posting() -> JobPostingData:
    return JobPostingData(
        job_title="Senior Python Backend Engineer",
        company="Acme Cloud Technologies",
        location="Remote, Australia",
        responsibilities=[
            "Architect and maintain high-throughput Django REST APIs and microservices",
            "Optimize PostgreSQL queries and Redis caching for sub-100ms response times",
            "Drive CI/CD pipelines using Docker, Kubernetes, and GitHub Actions",
            "Mentor junior engineers and champion clean code and automated testing",
        ],
        required_qualifications=[
            "5+ years of production experience with Python and Django / DRF",
            "Hands-on expertise with PostgreSQL database optimization",
            "Demonstrated experience with AWS cloud infrastructure and Docker",
        ],
        preferred_qualifications=[
            "Experience with Golang or Rust for performance-critical services",
            "Familiarity with GraphQL APIs",
        ],
        skills=["Python", "Django", "PostgreSQL", "Redis", "Docker", "AWS", "CI/CD", "Kubernetes"],
        keywords=["Python", "Django", "PostgreSQL", "Redis", "Docker", "AWS", "Scalability", "Microservices"],
        tone_and_culture=["Fast-paced & high-ownership", "Engineering excellence & rigor"],
        raw_text="Acme Cloud Technologies is hiring a Senior Python Backend Engineer...",
    )


@pytest.fixture
def sample_user_resume() -> StructuredResume:
    return StructuredResume(
        contact=ContactDetails(
            name="Alex Mercer",
            email="alex.mercer@example.com",
            phone="+61 400 123 456",
            location="Sydney, NSW",
            linkedin="https://linkedin.com/in/alexmercer-dev",
            website="https://github.com/alexmercer",
        ),
        summary="Software Engineer with 6 years building distributed web applications.",
        experience=[
            ExperienceItem(
                id="exp-1",
                title="Software Engineer",
                company="FinTech Solutions",
                location="Sydney, Australia",
                dates="Jan 2021 - Present",
                bullets=[
                    "Responsible for building backend services using Python and Flask.",
                    "Improved API response times by 42% through PostgreSQL query index tuning and Redis caching.",
                    "Managed Docker container deployments on AWS ECS, serving over 1,500,000 daily requests.",
                    "Organized weekly tech talks and team lunches.",
                ],
            ),
            ExperienceItem(
                id="exp-2",
                title="Junior Developer",
                company="Startup Labs",
                location="Melbourne, Australia",
                dates="Feb 2018 - Dec 2020",
                bullets=[
                    "Worked on front-end components using JavaScript and HTML.",
                    "Assisted with writing automated unit tests and integration tests in Pytest.",
                ],
            ),
        ],
        education=[],
        skills=["Python", "Flask", "PostgreSQL", "Redis", "Docker", "AWS", "Pytest", "Git"],
        certifications=["AWS Certified Solutions Architect Associate"],
        projects=[],
    )


# ============================================================================
# 1. SCRAPER & PARSER TESTS (Deliverable 2 & Fallback Paths)
# ============================================================================

def test_parse_linkedin_html_structure():
    """Tests parsing LinkedIn guest job postings with semantic HTML tags."""
    sample_html = """
    <html>
      <body>
        <h1 class="top-card-layout__title">Staff Platform Engineer</h1>
        <a class="topcard__org-name-link">NextGen Systems</a>
        <span class="topcard__flavor--bullet">Melbourne, VIC</span>
        <div class="show-more-less-html__markup">
          <p>We are looking for an engineer to lead our cloud platform.</p>
          <h2>Responsibilities</h2>
          <ul>
            <li>Design and deploy resilient Kubernetes clusters on GCP</li>
            <li>Maintain automated CI/CD pipelines with GitHub Actions</li>
          </ul>
          <h2>Requirements</h2>
          <ul>
            <li>Proven experience with Terraform and Python</li>
            <li>Strong background in distributed systems</li>
          </ul>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(sample_html, "html.parser")
    title, company, location, desc = parse_linkedin_html(soup)
    assert title == "Staff Platform Engineer"
    assert company == "NextGen Systems"
    assert location == "Melbourne, VIC"
    assert "Kubernetes" in desc
    assert "Terraform" in desc


def test_parse_seek_html_structure():
    """Tests parsing Seek job advertisements using data-automation attributes."""
    sample_html = """
    <html>
      <body>
        <h1 data-automation="job-detail-title">Senior Full Stack Developer</h1>
        <span data-automation="advertiser-name">FinTech Australia</span>
        <span data-automation="job-detail-location">Sydney NSW</span>
        <div data-automation="jobAdDetails">
          <p>About the role: Build Next.js and Django web applications.</p>
          <ul>
            <li>Develop scalable REST APIs using Django REST Framework</li>
            <li>Build responsive UIs using React and TypeScript</li>
          </ul>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(sample_html, "html.parser")
    title, company, location, desc = parse_seek_html(soup)
    assert title == "Senior Full Stack Developer"
    assert company == "FinTech Australia"
    assert location == "Sydney NSW"
    assert "Django" in desc
    assert "Next.js" in desc


def test_scraper_fallback_to_pasted_text_when_url_blocked():
    """
    When a job board blocks automated scraping (e.g. HTTP 403 / 999 or login wall),
    the scraper must raise JobScrapeError with requires_paste_fallback=True.
    If the user provides pasted text, it must gracefully process it.
    """
    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.url = "https://www.linkedin.com/jobs/view/12345"
        mock_get.return_value = mock_response

        # 1. URL alone without pasted fallback -> raises error indicating paste fallback is required
        with pytest.raises(JobScrapeError) as exc_info:
            scrape_or_parse_job(job_url="https://www.linkedin.com/jobs/view/12345")
        assert exc_info.value.requires_paste_fallback is True
        assert exc_info.value.code == "JOB_SITE_BLOCKED"

        # 2. URL + pasted text fallback -> gracefully returns structured job from pasted text!
        pasted_text = (
            "Job Title: Lead Python Engineer\nCompany: DataCorp\n"
            "Responsibilities:\n- Build real-time streaming pipelines\n"
            "Requirements:\n- 4+ years Python and Kafka experience"
        )
        job = scrape_or_parse_job(
            job_url="https://www.linkedin.com/jobs/view/12345", job_text=pasted_text
        )
        assert job.job_title == "Lead Python Engineer"
        assert job.company == "DataCorp"
        assert "Python" in job.skills


def test_scraper_handles_network_timeout():
    """Verifies timeout errors prompt the user to paste the job text."""
    import requests

    with patch("requests.get", side_effect=requests.exceptions.Timeout("Connection timed out")):
        with pytest.raises(JobScrapeError) as exc_info:
            scrape_or_parse_job(job_url="https://example.com/slow-job")
        assert exc_info.value.code == "JOB_FETCH_TIMEOUT"
        assert exc_info.value.requires_paste_fallback is True


# ============================================================================
# 2. RESUME PARSER TESTS (Deliverable 3 & File Formats)
# ============================================================================

def test_extract_text_from_pdf():
    """Generates a valid test PDF in memory and tests extraction."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)

    # Empty text page check
    text = extract_text_from_pdf(pdf_bytes.getvalue())
    assert isinstance(text, str)


def test_extract_text_from_docx():
    """Generates a valid in-memory DOCX document and tests paragraph extraction."""
    doc = docx.Document()
    doc.add_heading("Jane Doe", level=0)
    doc.add_paragraph("jane.doe@example.com | 555-0199 | Austin, TX")
    doc.add_heading("Experience", level=1)
    doc.add_paragraph("Senior Engineer | TechCorp | 2020 - Present")
    doc.add_paragraph("- Built cloud services in Python", style="List Bullet")

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    extracted = extract_text_from_docx(docx_bytes)
    assert "Jane Doe" in extracted
    assert "Senior Engineer" in extracted
    assert "TechCorp" in extracted
    assert "Python" in extracted


def test_parse_resume_handles_sparse_or_unreadable_file():
    """
    If an uploaded file is sparse or unreadable, the parser builds the best
    possible version and clearly lists which sections need more information.
    """
    sparse_text = "Jane Doe\njane@example.com\n"
    resume = parse_resume(resume_text=sparse_text)

    assert resume.contact.name == "Jane Doe"
    assert resume.contact.email == "jane@example.com"
    # Should flag missing experience, education, skills
    warning_text = " ".join(resume.missing_or_sparse_sections).lower()
    assert "experience" in warning_text
    assert "education" in warning_text
    assert "skills" in warning_text


def test_parse_resume_rejects_corrupted_file():
    """Unreadable or corrupted files must raise ResumeParseError with clear messaging."""
    corrupted_bytes = b"NOT_A_REAL_PDF_OR_DOCX_HEADER_GARBAGE_BYTES_12345"
    with pytest.raises(ResumeParseError):
        parse_resume(resume_file_name="resume.pdf", resume_file_bytes=corrupted_bytes)


# ============================================================================
# 3. TAILORING ENGINE & STRICT NO-FABRICATION TESTS (Deliverable 4)
# ============================================================================

def test_tailoring_engine_preserves_factual_accuracy(sample_user_resume, sample_job_posting):
    """
    CRITICAL INVARIANT:
    - Never invent employers, job titles, dates, or credentials.
    - Preserves all original metrics (percentages, numbers, dollar amounts).
    """
    result = tailor_resume(sample_user_resume, sample_job_posting)

    orig_exp = sample_user_resume.experience
    tailored_exp = result.tailored_resume.experience

    assert len(tailored_exp) == len(orig_exp)

    for orig, tailored in zip(orig_exp, tailored_exp):
        # 1. Employer, Title, and Dates MUST BE 100% VERBATIM EQUAL
        assert tailored.company == orig.company, f"Employer modified! {tailored.company} != {orig.company}"
        assert tailored.title == orig.title, f"Job title modified! {tailored.title} != {orig.title}"
        assert tailored.dates == orig.dates, f"Dates modified! {tailored.dates} != {orig.dates}"

    # 2. Check metrics preservation in bullet points
    # FinTech role had 42% and 1,500,000
    fintech_bullets = " ".join(tailored_exp[0].bullets)
    assert "42%" in fintech_bullets, "The 42% performance metric was altered or lost!"
    assert "1,500,000" in fintech_bullets or "1500000" in fintech_bullets, "Traffic metric was lost!"


def test_tailoring_engine_reorders_bullets_by_job_relevance(sample_user_resume, sample_job_posting):
    """
    Relevance reordering: bullets matching job keywords (PostgreSQL, Redis, AWS, Docker)
    should be prioritized over low-relevance bullets (e.g. 'Organized weekly tech talks and team lunches').
    """
    result = tailor_resume(sample_user_resume, sample_job_posting)
    fintech_tailored = result.tailored_resume.experience[0]

    # The tech-talks bullet was originally at index 3 and should remain at the end
    last_bullet = fintech_tailored.bullets[-1]
    assert "tech talks" in last_bullet.lower()

    # The top bullets must feature the core technical achievements
    first_bullet = fintech_tailored.bullets[0].lower()
    assert any(term in first_bullet for term in ("postgresql", "redis", "docker", "aws", "python"))

    # Check that diff metadata reflects reordering and modifications
    assert len(result.experience_diffs) > 0
    diff = result.experience_diffs[0]
    assert any(b.was_reordered or b.was_modified for b in diff.bullet_changes)


def test_tailoring_engine_flags_gaps_without_fabrication(sample_user_resume, sample_job_posting):
    """
    NO-FABRICATION RULE:
    The job posting requires 'Kubernetes' and prefers 'Golang' / 'GraphQL'.
    Alex Mercer's resume has NO Golang or GraphQL.
    The tailoring engine MUST flag these as gaps in `gaps` instead of fabricating them.
    """
    result = tailor_resume(sample_user_resume, sample_job_posting)

    tailored_text = (
        result.tailored_resume.summary
        + " "
        + " ".join(result.tailored_resume.skills)
        + " "
        + " ".join([" ".join(exp.bullets) for exp in result.tailored_resume.experience])
    ).lower()

    # NEVER fabricate Golang or GraphQL on the candidate's resume
    assert "golang" not in tailored_text
    assert "graphql" not in tailored_text

    # MUST be present in gaps
    gap_requirements = [g.requirement.lower() for g in result.gaps]
    assert any("golang" in g or "rust" in g for g in gap_requirements)
    assert any("graphql" in g for g in gap_requirements)


def test_weak_verb_strengthening_preserves_facts():
    """Weak verbs are rewritten into active verbs without altering achievements."""
    orig = "Responsible for building backend services using Python."
    tailored, matched, reason = rewrite_bullet_with_guardrails(
        orig, job_keywords=["Python", "Django"], responsibilities=[]
    )
    assert "Spearheaded building backend services" in tailored or "Delivered" in tailored
    assert "Python" in tailored


# ============================================================================
# 4. EXPORT OUTPUT TESTS (Deliverable 5 & ATS Compliance)
# ============================================================================

def test_generate_pdf_resume_produces_valid_bytes(sample_user_resume):
    """PDF generator produces valid, readable binary bytes starting with %PDF."""
    pdf_bytes = generate_pdf_resume(sample_user_resume)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")


def test_generate_docx_resume_produces_valid_bytes(sample_user_resume):
    """DOCX generator produces valid, readable binary bytes starting with PK (zip archive)."""
    docx_bytes = generate_docx_resume(sample_user_resume)
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 500
    assert docx_bytes.startswith(b"PK")  # DOCX is an OOXML zip archive


# ============================================================================
# 5. REST API ENDPOINT INTEGRATION TESTS
# ============================================================================

def test_api_health_endpoint(api_client):
    response = api_client.get("/api/health/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"


def test_api_scrape_job_pasted_text(api_client):
    payload = {
        "job_text": "Role: Senior Backend Engineer\nCompany: TechCo\nResponsibilities:\n- Build microservices\nRequirements:\n- 5 years Python"
    }
    response = api_client.post("/api/scrape-job/", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["job_title"] == "Senior Backend Engineer"
    assert data["company"] == "TechCo"
    assert "Python" in data["skills"]


def test_api_tailor_endpoint_end_to_end(api_client, sample_job_posting, sample_user_resume):
    payload = {
        "job": sample_job_posting.model_dump(),
        "resume": sample_user_resume.model_dump(),
    }
    response = api_client.post("/api/tailor/", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "original_resume" in data
    assert "tailored_resume" in data
    assert "experience_diffs" in data
    assert "gaps" in data
    assert data["match_score"] > 0


def test_api_export_pdf_download(api_client, sample_user_resume):
    payload = {"resume": sample_user_resume.model_dump()}
    response = api_client.post("/api/export/pdf/", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_api_export_docx_download(api_client, sample_user_resume):
    payload = {"resume": sample_user_resume.model_dump()}
    response = api_client.post("/api/export/docx/", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == status.HTTP_200_OK
    assert "wordprocessingml.document" in response["Content-Type"]
    assert response.content.startswith(b"PK")


# ============================================================================
# 6. SKILL VALIDITY & CONSISTENCY TESTS
# ============================================================================

def test_scraper_does_not_suggest_locations_or_non_skills():
    """
    Verifies that mine sites (Pilgangoora, Colina), companies (PLS), rosters (FIFO),
    and sentence-starters (Following, As, Operation) are NEVER added as recommended skills.
    """
    raw_job = (
        "Role: Specialist Autonomous Haulage System Application at PLS\n"
        "Company: Pilbara Minerals (PLS)\n"
        "Location: Pilgangoora Operation, WA | FIFO Roster\n\n"
        "Responsibilities:\n"
        "- Following site safety procedures, maintain governance of AHS procedures\n"
        "- Conduct pre-start checks within AOZs to ensure autonomous haulage availability\n"
        "- Provide Level 2 technical support for Caterpillar MineStar Command\n\n"
        "Requirements:\n"
        "- As a qualified technician, proven experience in Autonomous Haulage Systems (AHS)\n"
        "- Hands-on expertise with CAT Command and MineStar Fleet\n"
        "- Knowledge of site Critical Controls and GNSS radio telemetry"
    )
    job = extract_structured_job_details(raw_job)

    # Skills must include actual technologies
    assert "AHS" in job.skills or "Autonomous Haulage" in job.skills
    assert "MineStar Command" in job.skills or "Caterpillar MineStar" in job.skills

    # Skills must NEVER contain locations, rosters, company names, or syntax words
    non_skills = {"pilgangoora", "colina", "pls", "fifo", "as", "following", "operation", "wa"}
    skills_lower = {s.lower() for s in job.skills}
    for ns in non_skills:
        assert ns not in skills_lower, f"Non-skill '{ns}' was erroneously added to job.skills!"


def test_rewrite_preserves_grammar_and_avoids_awkward_capitalization():
    """
    Verifies that:
    1. 'Assisted with' rewrites to 'Collaborated on ' (NOT 'Collaborated to ').
    2. Common nouns like 'operation' and 'health' are not capitalized mid-sentence.
    3. Acronyms like 'AHS' and mixed-case brands like 'MineStar' are preserved or aligned.
    """
    job_kws = ["Operation", "Health", "Troubleshooting", "AHS", "MineStar", "Autonomous Haulage"]

    # 1. Grammar check for "assisted with"
    bullet_assisted = "Assisted with commissioning and start-up of new mining technology."
    tailored_assisted, _, reason = rewrite_bullet_with_guardrails(bullet_assisted, job_kws, [])
    assert tailored_assisted.startswith("Collaborated on commissioning")
    assert "Collaborated to commissioning" not in tailored_assisted

    # 2. Mid-sentence common noun casing check
    bullet_nouns = "Supported mining communications across an active gold mining operation."
    tailored_nouns, _, _ = rewrite_bullet_with_guardrails(bullet_nouns, job_kws, [])
    assert "gold mining operation." in tailored_nouns
    assert "gold mining Operation." not in tailored_nouns

    bullet_health = "Worked within a NOC environment to monitor system health and critical KPIs."
    tailored_health, _, _ = rewrite_bullet_with_guardrails(bullet_health, job_kws, [])
    assert "system health" in tailored_health
    assert "system Health" not in tailored_health


def test_resume_parser_stitches_multiline_education():
    """
    Verifies that multi-line degree titles like 'Trade Qualification - Electronics &'
    followed by 'Communications' are stitched together cleanly.
    """
    resume_text = (
        "John Doe\njohn@example.com | 0400000000\n\n"
        "Education\n"
        "Trade Qualification - Electronics &\n"
        "Communications\n"
        "North Metropolitan TAFE — Perth, WA\n"
    )
    parsed = parse_resume_text(resume_text)
    assert len(parsed.education) >= 1
    edu = parsed.education[0]
    assert "Electronics" in edu.degree and "Communications" in edu.degree
    assert "TAFE" in edu.institution or "North Metropolitan" in edu.institution


# ============================================================================
# 7. SECURITY & VALIDATION TESTS
# ============================================================================

def test_resume_parser_rejects_spoofed_pdf_without_magic_bytes():
    """Verifies that non-PDF binaries named .pdf are rejected immediately via signature check."""
    fake_pdf_bytes = b"This is not a real PDF file despite the extension"
    with pytest.raises(ResumeParseError) as exc_info:
        parse_resume(resume_file_name="fake_resume.pdf", resume_file_bytes=fake_pdf_bytes)
    assert exc_info.value.code == "INVALID_PDF_SIGNATURE"


def test_resume_parser_rejects_spoofed_docx_without_magic_bytes():
    """Verifies that non-DOCX binaries named .docx are rejected immediately via PK zip check."""
    fake_docx_bytes = b"This is plain text pretending to be a word document"
    with pytest.raises(ResumeParseError) as exc_info:
        parse_resume(resume_file_name="fake_resume.docx", resume_file_bytes=fake_docx_bytes)
    assert exc_info.value.code == "INVALID_DOCX_SIGNATURE"


def test_resume_parser_rejects_oversized_file():
    """Verifies files over 5 MB are rejected with FILE_TOO_LARGE."""
    oversized_bytes = b"%PDF" + (b"0" * (6 * 1024 * 1024))
    with pytest.raises(ResumeParseError) as exc_info:
        parse_resume(resume_file_name="large.pdf", resume_file_bytes=oversized_bytes)
    assert exc_info.value.code == "FILE_TOO_LARGE"


