import {
  JobPostingData,
  StructuredResume,
  TailoringResult,
  ApiErrorResponse,
} from "../types/resume";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  code?: string;
  requiresPasteFallback?: boolean;
  status: number;

  constructor(message: string, status: number, code?: string, requiresPasteFallback?: boolean) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requiresPasteFallback = requiresPasteFallback;
  }
}

/**
 * Robust fetch wrapper with timeout cancellation.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 30000
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return res;
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        "Request timed out. The server took too long to respond. Please check your network and try again.",
        408,
        "REQUEST_TIMEOUT"
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Scrapes or parses a job posting from a URL or raw text.
 */
export async function scrapeJobPosting(
  jobUrl?: string,
  jobText?: string
): Promise<JobPostingData> {
  const res = await fetchWithTimeout(`${BACKEND_URL}/api/scrape-job/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_url: jobUrl, job_text: jobText }),
  });

  const data = await res.json();
  if (!res.ok) {
    const errData = data as ApiErrorResponse;
    throw new ApiError(
      errData.error || "Failed to process job posting.",
      res.status,
      errData.code,
      errData.requires_paste_fallback
    );
  }
  return data as JobPostingData;
}

/**
 * Parses an uploaded resume file (PDF/DOCX) or pasted text into structured sections.
 */
export async function parseResumeInput(
  file?: File | null,
  pastedText?: string
): Promise<StructuredResume> {
  const formData = new FormData();
  if (file) {
    formData.append("resume_file", file);
  }
  if (pastedText) {
    formData.append("resume_text", pastedText);
  }

  const res = await fetchWithTimeout(`${BACKEND_URL}/api/parse-resume/`, {
    method: "POST",
    body: formData,
  });

  const data = await res.json();
  if (!res.ok) {
    const errData = data as ApiErrorResponse;
    throw new ApiError(errData.error || "Failed to parse resume.", res.status, errData.code);
  }
  return data as StructuredResume;
}

/**
 * End-to-end resume tailoring: maps resume to job, produces diffs, and flags gaps.
 */
export async function tailorResumeContent(
  job: JobPostingData,
  resume: StructuredResume
): Promise<TailoringResult> {
  const res = await fetchWithTimeout(`${BACKEND_URL}/api/tailor/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job, resume }),
  }, 45000); // Allow 45s for AI-assisted tailoring if enabled

  const data = await res.json();
  if (!res.ok) {
    const errData = data as ApiErrorResponse;
    throw new ApiError(
      errData.error || "Failed to tailor resume.",
      res.status,
      errData.code,
      errData.requires_paste_fallback
    );
  }
  return data as TailoringResult;
}

/**
 * Downloads the user-approved tailored resume as an ATS-compliant PDF.
 */
export async function downloadPdfResume(resume: StructuredResume, candidateName: string): Promise<void> {
  const res = await fetchWithTimeout(`${BACKEND_URL}/api/export/pdf/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume }),
  });

  if (!res.ok) {
    const errJson = await res.json().catch(() => ({}));
    throw new ApiError(errJson.error || "Failed to export PDF.", res.status);
  }

  const blob = await res.blob();
  const safeName = (candidateName || "Tailored").replace(/[^a-zA-Z0-9]/g, "_");
  triggerFileDownload(blob, `${safeName}_Resume.pdf`);
}

/**
 * Downloads the user-approved tailored resume as an ATS-compliant DOCX.
 */
export async function downloadDocxResume(resume: StructuredResume, candidateName: string): Promise<void> {
  const res = await fetchWithTimeout(`${BACKEND_URL}/api/export/docx/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume }),
  });

  if (!res.ok) {
    const errJson = await res.json().catch(() => ({}));
    throw new ApiError(errJson.error || "Failed to export Word document.", res.status);
  }

  const blob = await res.blob();
  const safeName = (candidateName || "Tailored").replace(/[^a-zA-Z0-9]/g, "_");
  triggerFileDownload(blob, `${safeName}_Resume.docx`);
}

function triggerFileDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.style.display = "none";
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  a.remove();
}
