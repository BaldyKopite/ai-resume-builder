/**
 * TypeScript definitions for AI Resume Builder
 * Synchronized with the Django backend Pydantic schemas.
 */

export interface ContactDetails {
  name: string;
  email: string;
  phone: string;
  location: string;
  linkedin: string;
  website: string;
}

export interface ExperienceItem {
  id: string;
  title: string;
  company: string;
  location: string;
  dates: string;
  bullets: string[];
}

export interface EducationItem {
  id: string;
  degree: string;
  institution: string;
  dates: string;
  details: string[];
}

export interface ProjectItem {
  id: string;
  name: string;
  description: string;
  dates: string;
  bullets: string[];
}

export interface StructuredResume {
  contact: ContactDetails;
  summary: string;
  experience: ExperienceItem[];
  education: EducationItem[];
  skills: string[];
  certifications: string[];
  projects: ProjectItem[];
  missing_or_sparse_sections: string[];
  raw_text?: string;
}

export interface JobPostingData {
  job_title: string;
  company: string;
  location: string;
  source_url: string;
  source_site: string;
  responsibilities: string[];
  required_qualifications: string[];
  preferred_qualifications: string[];
  skills: string[];
  keywords: string[];
  tone_and_culture: string[];
  raw_text?: string;
}

export interface BulletChange {
  original_index: number;
  new_index: number;
  original_text: string;
  tailored_text: string;
  matched_keywords: string[];
  change_reason: string;
  was_modified: boolean;
  was_reordered: boolean;
}

export interface ExperienceDiff {
  experience_id: string;
  company: string;
  title: string;
  dates: string;
  bullet_changes: BulletChange[];
}

export interface GapItem {
  requirement: string;
  category: "required" | "preferred" | "skill";
  status: "missing" | "partial";
  note: string;
}

export interface TailoringResult {
  job: JobPostingData;
  original_resume: StructuredResume;
  tailored_resume: StructuredResume;
  summary_change_reason: string;
  experience_diffs: ExperienceDiff[];
  matched_keywords: string[];
  missing_keywords: string[];
  gaps: GapItem[];
  sparse_section_warnings: string[];
  match_score: number;
  tailoring_mode: string;
}

export interface ApiErrorResponse {
  error: string;
  code?: string;
  requires_paste_fallback?: boolean;
  source_url?: string;
  details?: unknown;
}
