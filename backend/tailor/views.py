"""
Tailor Views (`views.py`)
=========================
REST API endpoints powering the Next.js frontend:
1. `POST /api/scrape-job/`: Fetches & parses job link (or pasted text), with explicit fallback handling.
2. `POST /api/parse-resume/`: Parses uploaded PDF/DOCX or pasted text into structured resume sections.
3. `POST /api/tailor/`: Runs tailoring engine, returns side-by-side original vs tailored content, diffs, & gaps.
4. `POST /api/export/pdf/`: Downloads ATS-friendly PDF.
5. `POST /api/export/docx/`: Downloads ATS-friendly DOCX.
6. `GET /api/health/`: System health check & engine mode verification.
"""
import json
import logging
from typing import Any, Dict

from django.http import HttpResponse
from pydantic import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from .schemas import JobPostingData, StructuredResume, TailoringResult
from .services.exporter import ExportError, generate_docx_resume, generate_pdf_resume
from .services.job_scraper import JobScrapeError, scrape_or_parse_job
from .services.resume_parser import ResumeParseError, parse_resume
from .services.tailoring_engine import tailor_resume

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health_check(request: Request) -> Response:
    """Returns backend status, version, and AI engine status."""
    from django.conf import settings

    has_gemini = bool(getattr(settings, "GEMINI_API_KEY", ""))
    return Response(
        {
            "status": "healthy",
            "service": "ai-resume-builder-backend",
            "gemini_ai_configured": has_gemini,
            "gemini_model": getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash"),
            "privacy_mode": "stateless-in-memory",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@parser_classes([JSONParser, FormParser])
def scrape_job_view(request: Request) -> Response:
    """
    Parses a job posting from a URL (LinkedIn, Seek, Generic) or direct pasted text.
    Returns 422 Unprocessable Entity with `requires_paste_fallback: true` when a job
    board blocks automated scraping or triggers a login wall.
    """
    data = request.data
    job_url = data.get("job_url", "")
    job_text = data.get("job_text", "")

    if not job_url and not job_text:
        return Response(
            {
                "error": "Please provide either a job URL or paste the job description text.",
                "code": "MISSING_JOB_INPUT",
                "requires_paste_fallback": True,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        job_data = scrape_or_parse_job(job_url=job_url, job_text=job_text)
        return Response(job_data.model_dump(), status=status.HTTP_200_OK)
    except JobScrapeError as exc:
        logger.info("Job scraping encountered fallback trigger: %s", exc.message)
        return Response(
            {
                "error": exc.message,
                "code": exc.code,
                "requires_paste_fallback": exc.requires_paste_fallback,
                "source_url": exc.source_url,
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except Exception as exc:
        logger.error("Unexpected error in scrape_job_view: %s", exc, exc_info=True)
        return Response(
            {
                "error": f"An unexpected error occurred while processing the job posting: {str(exc)}",
                "code": "JOB_PROCESSING_ERROR",
                "requires_paste_fallback": True,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def parse_resume_view(request: Request) -> Response:
    """
    Parses an uploaded resume file (PDF, DOCX) or pasted resume text into structured sections.
    Flags missing or sparse sections so the user can review and provide additional detail.
    """
    file_obj = request.FILES.get("resume_file")
    resume_text = request.data.get("resume_text", "")

    file_bytes = None
    file_name = None
    if file_obj:
        file_bytes = file_obj.read()
        file_name = file_obj.name

    if not file_obj and not resume_text:
        return Response(
            {
                "error": "Please upload a resume file (PDF or DOCX) or paste your resume text.",
                "code": "MISSING_RESUME_INPUT",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        structured_resume = parse_resume(
            resume_file_name=file_name,
            resume_file_bytes=file_bytes,
            resume_text=resume_text,
        )
        return Response(structured_resume.model_dump(), status=status.HTTP_200_OK)
    except ResumeParseError as exc:
        logger.warning("Resume parse error: %s", exc.message)
        return Response(
            {
                "error": exc.message,
                "code": exc.code,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        logger.error("Unexpected error parsing resume: %s", exc, exc_info=True)
        return Response(
            {
                "error": f"Failed to parse resume: {str(exc)}",
                "code": "RESUME_PARSE_FAILED",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def tailor_resume_view(request: Request) -> Response:
    """
    End-to-end tailoring endpoint:
    Accepts:
    - `job_url` or `job_text` (or pre-parsed `job` object)
    - `resume_file` or `resume_text` (or pre-parsed `resume` object)
    Returns:
    - `original_resume`: Structured baseline for side-by-side review
    - `tailored_resume`: Tailored output with relevance reordering and natural keywords
    - `experience_diffs`: Per-bullet diff metadata (was_modified, was_reordered, change_reason)
    - `gaps`: Missing requirements flagged without fabrication
    - `match_score`: Genuine evidence alignment score
    """
    data = request.data

    try:
        # 1. Resolve Job Posting Data
        if "job" in data and isinstance(data["job"], dict):
            job_data = JobPostingData.model_validate(data["job"])
        else:
            job_url = data.get("job_url", "")
            job_text = data.get("job_text", "")
            job_data = scrape_or_parse_job(job_url=job_url, job_text=job_text)

        # 2. Resolve Structured Resume
        if "resume" in data and isinstance(data["resume"], dict):
            resume_data = StructuredResume.model_validate(data["resume"])
        else:
            file_obj = request.FILES.get("resume_file")
            resume_text = data.get("resume_text", "")
            file_bytes = file_obj.read() if file_obj else None
            file_name = file_obj.name if file_obj else None
            resume_data = parse_resume(
                resume_file_name=file_name,
                resume_file_bytes=file_bytes,
                resume_text=resume_text,
            )

        # 3. Execute Tailoring Engine
        result: TailoringResult = tailor_resume(resume=resume_data, job=job_data)
        return Response(result.model_dump(), status=status.HTTP_200_OK)

    except JobScrapeError as exc:
        return Response(
            {
                "error": exc.message,
                "code": exc.code,
                "requires_paste_fallback": exc.requires_paste_fallback,
                "source_url": exc.source_url,
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except ResumeParseError as exc:
        return Response(
            {"error": exc.message, "code": exc.code},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ValidationError as exc:
        return Response(
            {"error": "Invalid schema data provided.", "details": exc.errors()},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        logger.error("Unexpected error during resume tailoring: %s", exc, exc_info=True)
        return Response(
            {"error": f"Resume tailoring failed: {str(exc)}", "code": "TAILORING_FAILED"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@parser_classes([JSONParser])
def export_pdf_view(request: Request) -> HttpResponse:
    """Generates and downloads an ATS-compliant PDF resume from the user-approved resume JSON."""
    try:
        resume_payload = request.data.get("resume") or request.data
        resume_obj = StructuredResume.model_validate(resume_payload)
        pdf_bytes = generate_pdf_resume(resume_obj)

        filename = f"{re_clean_filename(resume_obj.contact.name)}_Tailored_Resume.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response
    except ExportError as exc:
        return Response(
            {"error": exc.message, "code": "EXPORT_FAILED"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except ValidationError as exc:
        return Response(
            {"error": "Invalid resume data structure.", "details": exc.errors()},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        logger.error("PDF export error: %s", exc, exc_info=True)
        return Response(
            {"error": f"Failed to export PDF: {str(exc)}", "code": "EXPORT_FAILED"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@parser_classes([JSONParser])
def export_docx_view(request: Request) -> HttpResponse:
    """Generates and downloads an ATS-compliant DOCX resume from the user-approved resume JSON."""
    try:
        resume_payload = request.data.get("resume") or request.data
        resume_obj = StructuredResume.model_validate(resume_payload)
        docx_bytes = generate_docx_resume(resume_obj)

        filename = f"{re_clean_filename(resume_obj.contact.name)}_Tailored_Resume.docx"
        response = HttpResponse(
            docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response
    except ExportError as exc:
        return Response(
            {"error": exc.message, "code": "EXPORT_FAILED"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except ValidationError as exc:
        return Response(
            {"error": "Invalid resume data structure.", "details": exc.errors()},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        logger.error("DOCX export error: %s", exc, exc_info=True)
        return Response(
            {"error": f"Failed to export Word document: {str(exc)}", "code": "EXPORT_FAILED"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def re_clean_filename(name: str) -> str:
    """Cleans candidate name for safe download filenames."""
    if not name or not name.strip():
        return "ATS"
    clean = "".join([c if c.isalnum() else "_" for c in name.strip()])
    return clean[:30]
