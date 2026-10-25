"""URL routing for tailor app API."""
from django.urls import path

from .views import (
    export_docx_view,
    export_pdf_view,
    health_check,
    parse_resume_view,
    scrape_job_view,
    tailor_resume_view,
)

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("scrape-job/", scrape_job_view, name="scrape_job"),
    path("parse-resume/", parse_resume_view, name="parse_resume"),
    path("tailor/", tailor_resume_view, name="tailor_resume"),
    path("export/pdf/", export_pdf_view, name="export_pdf"),
    path("export/docx/", export_docx_view, name="export_docx"),
]
