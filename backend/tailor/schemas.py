"""
Data schemas for Job Postings, Structured Resumes, Tailoring Results, and Gap Analysis.
Uses Pydantic v2 for strict validation and Gemini Structured Output compatibility.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class JobPostingData(BaseModel):
    """Structured representation of a scraped or parsed job posting."""

    job_title: str = Field(default="", description="Title of the job role.")
    company: str = Field(default="", description="Hiring company or organization name.")
    location: str = Field(default="", description="Job location or remote status.")
    source_url: str = Field(default="", description="Original job posting URL if provided.")
    source_site: str = Field(
        default="text",
        description="Detected job board ('linkedin', 'seek', 'generic', or 'text').",
    )
    responsibilities: List[str] = Field(
        default_factory=list, description="Key job duties and responsibilities."
    )
    required_qualifications: List[str] = Field(
        default_factory=list, description="Must-have qualifications and experience."
    )
    preferred_qualifications: List[str] = Field(
        default_factory=list, description="Nice-to-have or preferred qualifications."
    )
    skills: List[str] = Field(
        default_factory=list, description="Technical and domain skills explicitly mentioned."
    )
    keywords: List[str] = Field(
        default_factory=list, description="High-priority ATS keywords and domain phrases."
    )
    tone_and_culture: List[str] = Field(
        default_factory=list,
        description="Signals about company culture, pace, values, and communication tone.",
    )
    raw_text: str = Field(default="", description="Cleaned raw text of the job description.")


class ContactDetails(BaseModel):
    """Candidate contact details. Must be preserved strictly without fabrication."""

    name: str = Field(default="", description="Candidate's full name.")
    email: str = Field(default="", description="Email address.")
    phone: str = Field(default="", description="Phone number.")
    location: str = Field(default="", description="City, State/Country or address.")
    linkedin: str = Field(default="", description="LinkedIn profile URL.")
    website: str = Field(default="", description="Portfolio, GitHub, or personal website URL.")


class ExperienceItem(BaseModel):
    """A single employment history entry. Employer, title, and dates are immutable facts."""

    id: str = Field(default="", description="Unique identifier for tracking diffs.")
    title: str = Field(default="", description="Job title held.")
    company: str = Field(default="", description="Employer / company name.")
    location: str = Field(default="", description="Location of role.")
    dates: str = Field(default="", description="Start and end dates exactly as stated.")
    bullets: List[str] = Field(
        default_factory=list, description="Achievement and responsibility bullet points."
    )


class EducationItem(BaseModel):
    """An education entry. Degree, institution, and dates are immutable facts."""

    id: str = Field(default="", description="Unique identifier.")
    degree: str = Field(default="", description="Degree, diploma, or major.")
    institution: str = Field(default="", description="University, college, or school name.")
    dates: str = Field(default="", description="Graduation date or date range.")
    details: List[str] = Field(
        default_factory=list, description="Honors, GPA, coursework, or thesis details."
    )


class ProjectItem(BaseModel):
    """A project entry from the resume."""

    id: str = Field(default="", description="Unique identifier.")
    name: str = Field(default="", description="Project title.")
    description: str = Field(default="", description="Brief project overview or technologies.")
    dates: str = Field(default="", description="Project dates if any.")
    bullets: List[str] = Field(default_factory=list, description="Project achievement bullets.")


class StructuredResume(BaseModel):
    """Complete structured representation of a resume."""

    contact: ContactDetails = Field(default_factory=ContactDetails)
    summary: str = Field(default="", description="Professional summary or objective statement.")
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    missing_or_sparse_sections: List[str] = Field(
        default_factory=list,
        description="Warnings for sections that are missing or need more detail from the user.",
    )
    raw_text: str = Field(default="", description="Extracted raw text from the resume.")


class BulletChange(BaseModel):
    """Tracks how a single bullet point was reordered or rewritten for side-by-side review."""

    original_index: int = Field(description="Original 0-based index in the experience entry.")
    new_index: int = Field(description="New 0-based index after relevance reordering.")
    original_text: str = Field(description="Exact original bullet point text.")
    tailored_text: str = Field(description="Tailored bullet point text.")
    matched_keywords: List[str] = Field(
        default_factory=list,
        description="Job keywords naturally supported and highlighted in this bullet.",
    )
    change_reason: str = Field(
        default="", description="Explanation of why this bullet was reordered or refined."
    )
    was_modified: bool = Field(default=False, description="True if text was edited.")
    was_reordered: bool = Field(default=False, description="True if position changed.")


class ExperienceDiff(BaseModel):
    """Diff metadata for a single experience entry."""

    experience_id: str
    company: str
    title: str
    dates: str
    bullet_changes: List[BulletChange] = Field(default_factory=list)


class GapItem(BaseModel):
    """A job requirement or skill that has no supporting evidence in the user's resume."""

    requirement: str = Field(description="The job requirement, qualification, or skill.")
    category: str = Field(
        default="required",
        description="'required', 'preferred', or 'skill'",
    )
    status: str = Field(
        default="missing",
        description="'missing' (no evidence found) or 'partial' (adjacent experience found).",
    )
    note: str = Field(
        description="Actionable advice explaining the gap without fabricating claims on the resume."
    )


class TailoringResult(BaseModel):
    """Full output of the tailoring engine: original, tailored, diff metadata, and gap analysis."""

    job: JobPostingData
    original_resume: StructuredResume
    tailored_resume: StructuredResume
    summary_change_reason: str = Field(default="")
    experience_diffs: List[ExperienceDiff] = Field(default_factory=list)
    matched_keywords: List[str] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    gaps: List[GapItem] = Field(default_factory=list)
    sparse_section_warnings: List[str] = Field(default_factory=list)
    match_score: int = Field(
        default=0, description="Estimated alignment percentage (0-100) based on genuine evidence."
    )
    tailoring_mode: str = Field(
        default="deterministic",
        description="Indicates whether 'gemini-ai' (with strict fact guardrails) or 'deterministic' engine was used.",
    )
