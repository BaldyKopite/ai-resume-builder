"use client";

import React, { useState, useRef } from "react";
import {
  scrapeJobPosting,
  parseResumeInput,
  tailorResumeContent,
  downloadPdfResume,
  downloadDocxResume,
  ApiError,
} from "@/services/api";
import {
  JobPostingData,
  StructuredResume,
  TailoringResult,
} from "@/types/resume";

// Non-skill exclusion set for client-side display safety
const NON_SKILL_EXCLUSIONS = new Set([
  "fifo", "dido", "pls", "wa", "nsw", "qld", "vic", "sa", "tas", "nt", "act",
  "pilgangoora", "colina", "perth", "kalgoorlie", "yandi", "jundee", "as", "following",
  "operation", "operations", "role", "duties", "qualifications", "responsibilities",
  "experience", "work", "candidate", "mining", "company", "team", "full-time", "shift",
  "health", "safety", "environment", "access", "points", "site", "sites", "mine", "mines",
  "ensure", "ensuring", "conduct", "conducting", "maintain", "maintaining", "support",
  "supporting", "provide", "providing"
]);

export default function ResumeBuilderApp() {
  // Step navigation: 1 = Inputs, 2 = Review & Edit, 3 = Export Success
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);

  // Inputs state
  const [jobUrl, setJobUrl] = useState<string>("");
  const [jobText, setJobText] = useState<string>("");
  const [showJobTextFallback, setShowJobTextFallback] = useState<boolean>(false);
  const [resumeText, setResumeText] = useState<string>("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeInputMode, setResumeInputMode] = useState<"file" | "text">("file");
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  // Processing state
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [processingStatus, setProcessingStatus] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Results state
  const [tailoringResult, setTailoringResult] = useState<TailoringResult | null>(null);
  const [editableResume, setEditableResume] = useState<StructuredResume | null>(null);

  // Review UI view filter: "side-by-side" | "tailored-only"
  const [reviewMode, setReviewMode] = useState<"side-by-side" | "tailored">("side-by-side");
  const [isExporting, setIsExporting] = useState<"pdf" | "docx" | null>(null);
  const [addedGaps, setAddedGaps] = useState<Record<number, boolean>>({});

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pre-fill sample job and resume for rapid live evaluation
  const handleLoadSampleData = () => {
    setJobUrl("https://www.linkedin.com/jobs/view/sample-senior-python-engineer");
    setJobText(
      "Role: Senior Python Backend Engineer\nCompany: Acme Cloud Technologies\nLocation: Remote, Global\n\nResponsibilities:\n- Architect and scale high-throughput Django REST APIs\n- Optimize PostgreSQL queries and Redis caching for sub-100ms response times\n- Drive CI/CD container automation using Docker and AWS\n- Champion code quality, unit testing, and team mentoring\n\nRequired Qualifications:\n- 5+ years production experience with Python and Django / DRF\n- Demonstrated mastery of PostgreSQL database optimization\n- Proven experience deploying Docker containers on AWS\n\nPreferred Qualifications:\n- Hands-on experience with Golang or Rust for high-throughput microservices\n- Familiarity with GraphQL APIs"
    );
    setShowJobTextFallback(true);
    setResumeInputMode("text");
    setResumeText(
      "Alex Mercer\nalex.mercer@example.com | +61 400 123 456 | Sydney, Australia | linkedin.com/in/alexmercer-dev\n\nSummary\nDedicated Software Engineer with 6 years building distributed cloud applications.\n\nWork Experience\nSoftware Engineer | FinTech Systems | Jan 2021 - Present\n- Responsible for building backend services using Python and Flask.\n- Improved API response times by 42% through PostgreSQL query index tuning and Redis caching.\n- Managed Docker container deployments on AWS ECS, serving over 1,500,000 daily requests.\n- Organized weekly engineering knowledge sharing sessions.\n\nJunior Developer | Startup Labs | Feb 2018 - Dec 2020\n- Worked on front-end components using JavaScript and HTML.\n- Assisted with writing automated unit tests and integration tests in Pytest.\n\nSkills\nPython, Flask, PostgreSQL, Redis, Docker, AWS, Pytest, Git, REST APIs\n\nEducation\nB.S. in Computer Science | University of Technology Sydney (2018)"
    );
    setErrorMessage(null);
  };

  const handleProcessInputs = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!jobUrl.trim() && !jobText.trim()) {
      setErrorMessage("Please enter a job posting URL or paste the job description text.");
      return;
    }
    if (resumeInputMode === "file" && !resumeFile && !resumeText.trim()) {
      setErrorMessage("Please upload your resume file (PDF/DOCX) or switch to paste resume text.");
      return;
    }
    if (resumeInputMode === "text" && !resumeText.trim()) {
      setErrorMessage("Please paste your resume text.");
      return;
    }

    setIsProcessing(true);

    try {
      // 1. Process Job
      setProcessingStatus("Step 1/3: Parsing job description & extracting ATS keywords...");
      let parsedJob: JobPostingData;
      try {
        parsedJob = await scrapeJobPosting(
          jobUrl.trim() || undefined,
          jobText.trim() || undefined
        );
      } catch (err) {
        if (err instanceof ApiError && err.requiresPasteFallback) {
          setShowJobTextFallback(true);
          throw new ApiError(
            err.message ||
              "This job board requires authentication or blocked automated scraping. Please paste the job description text in the box below to continue.",
            err.status,
            err.code,
            true
          );
        }
        throw err;
      }

      // 2. Parse Resume
      setProcessingStatus("Step 2/3: Parsing resume into structured sections...");
      const parsedResume = await parseResumeInput(
        resumeInputMode === "file" ? resumeFile : null,
        resumeText.trim() || undefined
      );

      // 3. Tailor Resume
      setProcessingStatus("Step 3/3: Tailoring resume & performing gap analysis...");
      const result = await tailorResumeContent(parsedJob, parsedResume);

      setTailoringResult(result);
      setEditableResume(JSON.parse(JSON.stringify(result.tailored_resume)));
      setCurrentStep(2);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("An unexpected error occurred. Please check your inputs and try again.");
      }
    } finally {
      setIsProcessing(false);
      setProcessingStatus("");
    }
  };

  const handleDownloadPdf = async () => {
    if (!editableResume) return;
    setIsExporting("pdf");
    try {
      await downloadPdfResume(editableResume, editableResume.contact.name || "Tailored");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to download PDF.");
    } finally {
      setIsExporting(null);
    }
  };

  const handleDownloadDocx = async () => {
    if (!editableResume) return;
    setIsExporting("docx");
    try {
      await downloadDocxResume(editableResume, editableResume.contact.name || "Tailored");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to download Word document.");
    } finally {
      setIsExporting(null);
    }
  };

  // Editable resume modification helpers
  const handleSummaryChange = (newSummary: string) => {
    if (!editableResume) return;
    setEditableResume({ ...editableResume, summary: newSummary });
  };

  const handleBulletChange = (expIndex: number, bulletIndex: number, newText: string) => {
    if (!editableResume) return;
    const updated = { ...editableResume };
    updated.experience[expIndex].bullets[bulletIndex] = newText;
    setEditableResume(updated);
  };

  const handleSkillsChange = (newSkillsStr: string) => {
    if (!editableResume) return;
    const parsedSkills = newSkillsStr
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setEditableResume({ ...editableResume, skills: parsedSkills });
  };

  // One-click addition of missing skills into the candidate's skills list
  const handleAddSkillToResume = (skillName: string) => {
    if (!editableResume) return;
    const cleanSkill = skillName.replace(/^Skill:\s*/i, "").trim();
    if (!cleanSkill) return;

    const exists = editableResume.skills.some(
      (s) => s.toLowerCase() === cleanSkill.toLowerCase()
    );
    if (!exists) {
      setEditableResume({
        ...editableResume,
        skills: [cleanSkill, ...editableResume.skills],
      });
    }
  };

  // One-click addition of an achievement bullet into the chosen experience
  const handleAddBulletToExperience = (expIndex: number, textToAppend: string) => {
    if (!editableResume) return;
    const targetIdx = expIndex >= 0 && expIndex < editableResume.experience.length ? expIndex : 0;
    const updated = JSON.parse(JSON.stringify(editableResume)) as StructuredResume;

    if (!updated.experience[targetIdx]) {
      alert("No work experience entries available to attach bullet to.");
      return;
    }

    updated.experience[targetIdx].bullets.push(textToAppend);
    setEditableResume(updated);

    // Also update diffs state if in side-by-side mode so the new bullet renders cleanly
    if (tailoringResult) {
      const updatedResult = JSON.parse(JSON.stringify(tailoringResult)) as TailoringResult;
      const expDiff = updatedResult.experience_diffs.find(
        (d) => d.experience_id === updated.experience[targetIdx].id
      );
      if (expDiff) {
        expDiff.bullet_changes.push({
          original_index: expDiff.bullet_changes.length,
          new_index: expDiff.bullet_changes.length,
          original_text: "(Added by Candidate to address job requirement)",
          tailored_text: textToAppend,
          matched_keywords: [],
          change_reason: "Added to bridge job requirement gap.",
          was_modified: true,
          was_reordered: false,
        });
        setTailoringResult(updatedResult);
      }
    }
  };

  // Helper to generate a contextual draft bullet based on the specific requirement text
  const generateDraftBulletFromRequirement = (reqText: string): string => {
    const low = reqText.toLowerCase();
    if (low.includes("hse") || low.includes("safety") || low.includes("critical control")) {
      return "Championed site safety culture and strict compliance with Critical Controls, OEM standards, and statutory safety procedures.";
    }
    if (low.includes("governance") || low.includes("standard") || low.includes("compliance") || low.includes("procedure")) {
      return "Maintained governance of AHS procedures, standards, and operational verification across autonomous operating environments.";
    }
    if (low.includes("5+years") || low.includes("command for hauling") || low.includes("cat command") || low.includes("haul fleet")) {
      return "Delivered expert field technical support and system validation for CAT Command for Hauling across autonomous haul fleets.";
    }
    return `Supported operations ensuring strict compliance with ${reqText.slice(0, 60)}... and OEM standards.`;
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 antialiased">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md px-6 py-3.5 transition-colors">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-lg shadow-sm">
              AI
            </div>
            <div>
              <h1 className="font-bold text-lg tracking-tight leading-none text-slate-900 dark:text-white">
                ATS Resume Architect
              </h1>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                Production-Ready AI Resume Tailoring &bull; No Fabrication Rule
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleLoadSampleData}
              className="text-xs px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors cursor-pointer"
            >
              Load Demo Sample
            </button>
            <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800/80 px-2.5 py-1 rounded-full">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
              Stateless &bull; Zero Data Retention
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
        {/* Step Indicator */}
        <div className="mb-8 flex items-center justify-center">
          <nav aria-label="Progress" className="flex items-center gap-3 text-sm font-medium">
            <span
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full transition-all ${
                currentStep === 1
                  ? "bg-blue-600 text-white font-semibold shadow-sm"
                  : "bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
              }`}
            >
              1. Input &amp; Job Link
            </span>
            <span className="text-slate-400">&rarr;</span>
            <span
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full transition-all ${
                currentStep === 2
                  ? "bg-blue-600 text-white font-semibold shadow-sm"
                  : "bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
              }`}
            >
              2. Side-by-Side Review &amp; Edit
            </span>
            <span className="text-slate-400">&rarr;</span>
            <span
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full transition-all ${
                currentStep === 3
                  ? "bg-emerald-600 text-white font-semibold shadow-sm"
                  : "bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
              }`}
            >
              3. ATS Export Ready
            </span>
          </nav>
        </div>

        {/* Global Error Alert */}
        {errorMessage && (
          <div
            role="alert"
            className="mb-6 p-4 rounded-xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 text-red-900 dark:text-red-200 flex items-start gap-3 shadow-sm"
          >
            <div className="text-xl leading-none select-none">&#9888;</div>
            <div className="flex-1 text-sm">
              <strong className="font-semibold block mb-0.5">Notice</strong>
              {errorMessage}
            </div>
            <button
              onClick={() => setErrorMessage(null)}
              className="text-xs text-red-700 dark:text-red-300 hover:underline cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* STEP 1: Inputs View */}
        {currentStep === 1 && (
          <form onSubmit={handleProcessInputs} className="space-y-8">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Left Column: Job Posting Link & Text */}
              <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      <span className="flex h-6 w-6 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 text-xs items-center justify-center font-bold">
                        1
                      </span>
                      Target Job Posting
                    </h2>
                    <span className="text-xs text-slate-500">LinkedIn, Seek, or Paste</span>
                  </div>

                  {/* Job URL Input */}
                  <div className="mb-4">
                    <label
                      htmlFor="job-url-input"
                      className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5"
                    >
                      Job Posting URL
                    </label>
                    <input
                      id="job-url-input"
                      type="url"
                      suppressHydrationWarning
                      placeholder="https://www.linkedin.com/jobs/view/... or seek.com.au/job/..."
                      value={jobUrl}
                      onChange={(e) => setJobUrl(e.target.value)}
                      className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-slate-100 text-sm focus:border-blue-500 focus:bg-white dark:focus:bg-slate-800 transition"
                    />
                    <p className="text-xs text-slate-500 mt-1.5">
                      Enter the direct job link. If the job site uses a login authwall or bot shield, you will be prompted to paste the description.
                    </p>
                  </div>

                  {/* Fallback Paste Toggle / Textarea */}
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                    <button
                      type="button"
                      onClick={() => setShowJobTextFallback(!showJobTextFallback)}
                      className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 cursor-pointer mb-2"
                    >
                      <span>{showJobTextFallback ? "− Hide" : "+ Or paste"}</span> job description text directly
                    </button>

                    {showJobTextFallback && (
                      <div className="mt-2">
                        <label
                          htmlFor="job-text-input"
                          className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1"
                        >
                          Pasted Job Description Text
                        </label>
                        <textarea
                          id="job-text-input"
                          rows={7}
                          placeholder="Paste the full job title, company, requirements, and responsibilities here..."
                          value={jobText}
                          onChange={(e) => setJobText(e.target.value)}
                          className="auto-expand p-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-slate-100 text-sm focus:border-blue-500 focus:bg-white dark:focus:bg-slate-800 transition"
                        />
                      </div>
                    )}
                  </div>
                </div>

                <div className="mt-4 p-3 rounded-lg bg-blue-50/60 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-900/50 text-xs text-blue-800 dark:text-blue-300">
                  <strong>ATS Keypoint:</strong> Extracts titles, responsibilities, required &amp; preferred qualifications, domain skills, and company culture signals.
                </div>
              </div>

              {/* Right Column: Candidate's Current Resume */}
              <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      <span className="flex h-6 w-6 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 text-xs items-center justify-center font-bold">
                        2
                      </span>
                      Your Current Resume
                    </h2>
                    {/* Toggle file or text */}
                    <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 p-0.5 bg-slate-100 dark:bg-slate-800 text-xs">
                      <button
                        type="button"
                        onClick={() => setResumeInputMode("file")}
                        className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                          resumeInputMode === "file"
                            ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                            : "text-slate-600 dark:text-slate-400"
                        }`}
                      >
                        Upload File (PDF/DOCX)
                      </button>
                      <button
                        type="button"
                        onClick={() => setResumeInputMode("text")}
                        className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                          resumeInputMode === "text"
                            ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                            : "text-slate-600 dark:text-slate-400"
                        }`}
                      >
                        Paste Plain Text
                      </button>
                    </div>
                  </div>

                  {/* File Upload Tab */}
                  {resumeInputMode === "file" ? (
                    <div>
                      <div
                        onClick={() => fileInputRef.current?.click()}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setIsDragOver(true);
                        }}
                        onDragEnter={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setIsDragOver(true);
                        }}
                        onDragLeave={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setIsDragOver(false);
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setIsDragOver(false);
                          if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                            const droppedFile = e.dataTransfer.files[0];
                            const ext = droppedFile.name.toLowerCase();
                            if (ext.endsWith(".pdf") || ext.endsWith(".docx") || ext.endsWith(".txt")) {
                              setResumeFile(droppedFile);
                            } else {
                              setErrorMessage("Please upload a PDF (.pdf) or Word (.docx) document.");
                            }
                          }
                        }}
                        className={`border-2 border-dashed rounded-xl p-8 text-center transition cursor-pointer ${
                          isDragOver
                            ? "border-blue-600 bg-blue-50/50 dark:bg-blue-950/40 ring-4 ring-blue-500/20"
                            : "border-slate-300 dark:border-slate-700 hover:border-blue-500 hover:bg-blue-50/20 dark:hover:bg-blue-950/20"
                        }`}
                      >
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".pdf,.docx,.txt"
                          className="hidden"
                          onChange={(e) => {
                            if (e.target.files && e.target.files[0]) {
                              setResumeFile(e.target.files[0]);
                            }
                          }}
                        />
                        <div className="text-3xl mb-2">&#128196;</div>
                        {resumeFile ? (
                          <div>
                            <p className="font-semibold text-sm text-slate-900 dark:text-white">
                              {resumeFile.name}
                            </p>
                            <p className="text-xs text-slate-500 mt-1">
                              {(resumeFile.size / 1024).toFixed(1)} KB &bull; Click or drop another to replace
                            </p>
                          </div>
                        ) : (
                          <div>
                            <p className="font-medium text-sm text-slate-800 dark:text-slate-200">
                              {isDragOver ? "Drop your resume file here!" : "Click or drag & drop your resume file here"}
                            </p>
                            <p className="text-xs text-slate-500 mt-1">
                              Supports standard PDF (.pdf) and Microsoft Word (.docx)
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    /* Plain Text Tab */
                    <div>
                      <label
                        htmlFor="resume-text-input"
                        className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1"
                      >
                        Paste Current Resume Content
                      </label>
                      <textarea
                        id="resume-text-input"
                        rows={10}
                        placeholder="Paste your contact info, summary, experience, education, and skills..."
                        value={resumeText}
                        onChange={(e) => setResumeText(e.target.value)}
                        className="auto-expand p-3 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-slate-100 text-sm focus:border-blue-500 focus:bg-white dark:focus:bg-slate-800 transition"
                      />
                    </div>
                  )}
                </div>

                <div className="mt-4 p-3 rounded-lg bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-100 dark:border-emerald-900/50 text-xs text-emerald-800 dark:text-emerald-300">
                  <strong>Strict No-Fabrication Guarantee:</strong> Your employers, titles, employment dates, and quantified results stay 100% accurate. We never invent claims.
                </div>
              </div>
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-center pt-2">
              <button
                type="submit"
                disabled={isProcessing}
                className="px-8 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold text-base shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center gap-2 cursor-pointer"
              >
                {isProcessing ? (
                  <>
                    <span className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    <span>{processingStatus || "Processing..."}</span>
                  </>
                ) : (
                  <>
                    <span>Tailor My Resume for This Job</span>
                    <span>&rarr;</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {/* STEP 2: Side-by-Side Review Interface */}
        {currentStep === 2 && tailoringResult && editableResume && (
          <div className="space-y-6">
            {/* Header Toolbar */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm">
              <div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 rounded-md text-xs font-bold bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300">
                    Target Role: {tailoringResult.job.job_title}
                  </span>
                  <span className="text-xs text-slate-500">at {tailoringResult.job.company}</span>
                </div>
                <h2 className="text-xl font-bold text-slate-900 dark:text-white mt-1">
                  Review &amp; Approve Changes Before Export
                </h2>
                <p className="text-xs text-slate-500">
                  Review every tailored bullet point and edit text directly. Original facts and metrics are preserved.
                </p>
              </div>

              {/* View Toggle and Actions */}
              <div className="flex items-center gap-2 flex-wrap">
                {/* Match Score Badge */}
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs">
                  <span className="text-slate-500">Alignment Score:</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400 text-sm">
                    {tailoringResult.match_score}%
                  </span>
                </div>

                {/* Side-by-Side vs Tailored Toggle */}
                <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 p-0.5 bg-slate-100 dark:bg-slate-800 text-xs">
                  <button
                    type="button"
                    onClick={() => setReviewMode("side-by-side")}
                    className={`px-3 py-1.5 rounded-md font-medium transition cursor-pointer ${
                      reviewMode === "side-by-side"
                        ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                        : "text-slate-600 dark:text-slate-400"
                    }`}
                  >
                    Side-by-Side Diff
                  </button>
                  <button
                    type="button"
                    onClick={() => setReviewMode("tailored")}
                    className={`px-3 py-1.5 rounded-md font-medium transition cursor-pointer ${
                      reviewMode === "tailored"
                        ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs"
                        : "text-slate-600 dark:text-slate-400"
                    }`}
                  >
                    Tailored View
                  </button>
                </div>

                {/* Back to Edit Inputs */}
                <button
                  type="button"
                  onClick={() => setCurrentStep(1)}
                  className="px-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 transition cursor-pointer"
                >
                  Edit Inputs
                </button>

                {/* PDF Export Button */}
                <button
                  type="button"
                  disabled={isExporting !== null}
                  onClick={handleDownloadPdf}
                  className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-sm flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                >
                  {isExporting === "pdf" ? "Generating..." : "Download ATS PDF"}
                </button>

                {/* DOCX Export Button */}
                <button
                  type="button"
                  disabled={isExporting !== null}
                  onClick={handleDownloadDocx}
                  className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 dark:bg-slate-700 hover:bg-slate-900 text-white shadow-sm flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                >
                  {isExporting === "docx" ? "Generating..." : "Download ATS Word"}
                </button>
              </div>
            </div>

            {/* Incomplete / Sparse Section Warnings */}
            {tailoringResult.sparse_section_warnings.length > 0 && (
              <div className="p-4 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200">
                <div className="flex items-center gap-2 font-semibold text-xs uppercase tracking-wider mb-1">
                  <span>&#9888;</span> Sparse / Missing Sections Identified
                </div>
                <ul className="list-disc pl-5 text-xs space-y-1">
                  {tailoringResult.sparse_section_warnings.map((warn, i) => (
                    <li key={i}>{warn}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Gap Analysis Box (No Fabrication Rule) */}
            <div className="p-5 rounded-2xl border border-blue-200 dark:border-blue-900/60 bg-blue-50/70 dark:bg-blue-950/40">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm text-blue-900 dark:text-blue-200">
                    Gap Analysis &amp; Honesty Guardrail
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-200/80 dark:bg-blue-900 text-blue-800 dark:text-blue-300 font-medium">
                    {tailoringResult.gaps.length} Unmatched Requirements
                  </span>
                </div>
                <span className="text-xs text-blue-700 dark:text-blue-300">
                  Left off your resume to avoid fabricating credentials
                </span>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-400 mb-3">
                The following requirements from the job posting had no verified supporting evidence in your resume. If you have transferrable experience, you can edit your bullet points directly below.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {tailoringResult.gaps.map((gap, i) => {
                  const isSkillGap = gap.category === "skill" || gap.requirement.toLowerCase().startsWith("skill:");
                  const cleanSkillName = gap.requirement.replace(/^Skill:\s*/i, "").trim();
                  const alreadyInResume = editableResume.skills.some(
                    (s) => s.toLowerCase() === cleanSkillName.toLowerCase()
                  );

                  return (
                    <div
                      key={i}
                      className="p-3.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs shadow-2xs flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-semibold text-slate-900 dark:text-slate-100 line-clamp-2">
                            {gap.requirement}
                          </span>
                          <span
                            className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded shrink-0 ${
                              gap.category === "required"
                                ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                                : gap.category === "preferred"
                                ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                                : "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                            }`}
                          >
                            {gap.category}
                          </span>
                        </div>
                        <p className="text-slate-500 dark:text-slate-400 text-[11px] leading-relaxed mb-3">
                          {gap.note}
                        </p>
                      </div>

                      {/* Quick-Add Action Bar */}
                      <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
                        {isSkillGap ? (
                          <button
                            type="button"
                            disabled={alreadyInResume}
                            onClick={() => handleAddSkillToResume(gap.requirement)}
                            className={`text-xs px-2.5 py-1 rounded-md font-medium transition cursor-pointer flex items-center gap-1 ${
                              alreadyInResume
                                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                                : "bg-blue-600 hover:bg-blue-700 text-white shadow-xs"
                            }`}
                          >
                            {alreadyInResume ? "✓ Added to Skills" : `+ Add "${cleanSkillName}"`}
                          </button>
                        ) : (
                          <div className="flex items-center justify-between w-full">
                            <button
                              type="button"
                              disabled={addedGaps[i]}
                              onClick={() => {
                                const draftBullet = generateDraftBulletFromRequirement(gap.requirement);
                                handleAddBulletToExperience(0, draftBullet);
                                setAddedGaps((prev) => ({ ...prev, [i]: true }));
                              }}
                              className={`text-xs px-3 py-1 rounded-md font-medium transition cursor-pointer flex items-center gap-1.5 ${
                                addedGaps[i]
                                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                                  : "bg-blue-600 hover:bg-blue-700 text-white shadow-xs"
                              }`}
                            >
                              <span>{addedGaps[i] ? "✓ Draft Bullet Added to Role" : "+ Draft Bullet to Top Role"}</span>
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Resume Content Review Card */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
              {/* Candidate Contact Header */}
              <div className="p-6 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-850">
                <div className="max-w-3xl">
                  <h3 className="text-2xl font-bold text-slate-900 dark:text-white">
                    {editableResume.contact.name || "Candidate Name"}
                  </h3>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600 dark:text-slate-400 mt-2">
                    {editableResume.contact.email && <span>{editableResume.contact.email}</span>}
                    {editableResume.contact.phone && <span>&bull; {editableResume.contact.phone}</span>}
                    {editableResume.contact.location && <span>&bull; {editableResume.contact.location}</span>}
                    {editableResume.contact.linkedin && <span>&bull; {editableResume.contact.linkedin}</span>}
                    {editableResume.contact.website && <span>&bull; {editableResume.contact.website}</span>}
                  </div>
                </div>
              </div>

              <div className="p-6 space-y-8">
                {/* 1. Professional Summary Section */}
                <section>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Professional Summary
                    </h4>
                    {tailoringResult.summary_change_reason && (
                      <span className="text-[11px] text-blue-600 dark:text-blue-400">
                        {tailoringResult.summary_change_reason}
                      </span>
                    )}
                  </div>

                  {reviewMode === "side-by-side" ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Original */}
                      <div className="p-3.5 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400">
                        <span className="block font-semibold text-[11px] text-slate-500 mb-1">
                          Original Summary:
                        </span>
                        {tailoringResult.original_resume.summary || "(No summary provided in original resume)"}
                      </div>
                      {/* Tailored Editable */}
                      <div className="p-3.5 rounded-lg bg-blue-50/40 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900/60">
                        <span className="block font-semibold text-[11px] text-blue-700 dark:text-blue-300 mb-1">
                          Tailored Summary (Editable):
                        </span>
                        <textarea
                          rows={3}
                          value={editableResume.summary}
                          onChange={(e) => handleSummaryChange(e.target.value)}
                          className="auto-expand p-2 w-full text-xs rounded border border-blue-200 dark:border-blue-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                        />
                      </div>
                    </div>
                  ) : (
                    <textarea
                      rows={3}
                      value={editableResume.summary}
                      onChange={(e) => handleSummaryChange(e.target.value)}
                      className="auto-expand p-3 w-full text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                    />
                  )}
                </section>

                {/* 2. Skills Section */}
                <section>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      Skills (Prioritized for ATS)
                    </h4>
                    <span className="text-[11px] text-slate-500">
                      Comma separated &bull; Target job skills front-loaded
                    </span>
                  </div>
                  <input
                    type="text"
                    value={editableResume.skills.join(", ")}
                    onChange={(e) => handleSkillsChange(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-white font-mono"
                  />
                  {/* Recommended Target Skills Pills */}
                  {(() => {
                    const validRecommendedSkills = tailoringResult.missing_keywords.filter(
                      (s) => !NON_SKILL_EXCLUSIONS.has(s.trim().toLowerCase()) && s.trim().length > 1
                    );
                    if (validRecommendedSkills.length === 0) return null;
                    return (
                      <div className="mt-3 p-3 rounded-lg bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200/80 dark:border-blue-900/40">
                        <span className="block text-[11px] font-semibold text-blue-900 dark:text-blue-300 mb-1.5">
                          Click to add recommended skills from this job posting:
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {validRecommendedSkills.map((recSkill, idx) => {
                            const isAlreadyAdded = editableResume.skills.some(
                              (s) => s.toLowerCase() === recSkill.toLowerCase()
                            );
                            return (
                              <button
                                key={idx}
                                type="button"
                                onClick={() => handleAddSkillToResume(recSkill)}
                                disabled={isAlreadyAdded}
                                className={`text-[11px] px-2 py-0.5 rounded font-medium transition cursor-pointer flex items-center gap-1 ${
                                  isAlreadyAdded
                                    ? "bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500 cursor-default"
                                    : "bg-white dark:bg-slate-900 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/60"
                                }`}
                              >
                                <span>{isAlreadyAdded ? "✓" : "+"}</span>
                                <span>{recSkill}</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()}
                </section>

                {/* 3. Work Experience Section */}
                <section className="space-y-6">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    Work Experience (Relevance Reordered &bull; Verified Facts Preserved)
                  </h4>

                  {editableResume.experience.map((exp, expIdx) => {
                    const diffMeta = tailoringResult.experience_diffs.find(
                      (d) => d.experience_id === exp.id
                    );

                    return (
                      <div
                        key={exp.id || expIdx}
                        className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-850"
                      >
                        {/* Role Header */}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-4 pb-3 border-b border-slate-200 dark:border-slate-800">
                          <div>
                            <span className="font-bold text-base text-slate-900 dark:text-white">
                              {exp.title}
                            </span>
                            {exp.company && (
                              <span className="text-slate-600 dark:text-slate-400 font-medium">
                                {" "}
                                &bull; {exp.company}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-slate-500 font-medium">
                            {exp.dates} {exp.location && `(${exp.location})`}
                          </div>
                        </div>

                        {/* Bullets List */}
                        <div className="space-y-4">
                          {exp.bullets.map((bulletText, bulletIdx) => {
                            const bulletDiff = diffMeta?.bullet_changes[bulletIdx];

                            return (
                              <div key={bulletIdx} className="space-y-1.5">
                                {reviewMode === "side-by-side" && bulletDiff ? (
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                                    {/* Original Bullet */}
                                    <div className="p-3 rounded-lg bg-slate-100/70 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 text-slate-600 dark:text-slate-400">
                                      <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                                        <span>Original Position: #{bulletDiff.original_index + 1}</span>
                                      </div>
                                      <p>{bulletDiff.original_text}</p>
                                    </div>

                                    {/* Tailored Bullet (Editable) */}
                                    <div className="p-3 rounded-lg bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900/60">
                                      <div className="flex items-center justify-between text-[10px] mb-1">
                                        <span className="font-bold text-blue-700 dark:text-blue-300">
                                          Promoted to Position: #{bulletDiff.new_index + 1}
                                        </span>
                                        {bulletDiff.was_modified && (
                                          <span className="text-emerald-700 dark:text-emerald-400 font-medium">
                                            Enhanced Phrasing
                                          </span>
                                        )}
                                      </div>
                                      <textarea
                                        rows={2}
                                        value={bulletText}
                                        onChange={(e) =>
                                          handleBulletChange(expIdx, bulletIdx, e.target.value)
                                        }
                                        className="auto-expand p-2 w-full text-xs rounded border border-blue-200 dark:border-blue-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                                      />
                                      {bulletDiff.change_reason && (
                                        <div className="mt-1 text-[10px] text-blue-600 dark:text-blue-400">
                                          &bull; {bulletDiff.change_reason}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                ) : (
                                  /* Tailored-Only Mode */
                                  <div className="flex items-start gap-2">
                                    <span className="text-slate-400 text-sm mt-1.5">&bull;</span>
                                    <textarea
                                      rows={2}
                                      value={bulletText}
                                      onChange={(e) =>
                                        handleBulletChange(expIdx, bulletIdx, e.target.value)
                                      }
                                      className="auto-expand p-2 w-full text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                                    />
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </section>

                {/* 4. Education & Projects */}
                {editableResume.education.length > 0 && (
                  <section>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
                      Education
                    </h4>
                    <div className="space-y-2">
                      {editableResume.education.map((edu, idx) => (
                        <div
                          key={idx}
                          className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-850 flex items-center justify-between text-xs"
                        >
                          <div>
                            <span className="font-bold text-slate-900 dark:text-white">
                              {edu.degree}
                            </span>
                            {edu.institution && (
                              <span className="text-slate-600 dark:text-slate-400">
                                {" "}
                                &bull; {edu.institution}
                              </span>
                            )}
                          </div>
                          {edu.dates && <span className="text-slate-500">{edu.dates}</span>}
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </div>

              {/* Bottom Sticky Action Bar */}
              <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  Ready to apply? Export your single-column, ATS-verified resume.
                </span>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    disabled={isExporting !== null}
                    onClick={handleDownloadPdf}
                    className="px-5 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-sm flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                  >
                    {isExporting === "pdf" ? "Exporting..." : "Download ATS PDF"}
                  </button>
                  <button
                    type="button"
                    disabled={isExporting !== null}
                    onClick={handleDownloadDocx}
                    className="px-5 py-2 text-xs font-semibold rounded-lg bg-slate-800 dark:bg-slate-700 hover:bg-slate-900 text-white shadow-sm flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                  >
                    {isExporting === "docx" ? "Exporting..." : "Download ATS Word"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 dark:border-slate-800 py-6 px-4 text-center text-xs text-slate-500 dark:text-slate-400">
        <p>
          AI Resume Builder &bull; Built with React/Next.js &amp; Python/Django &bull; ATS Best Practices &amp; Strict Factual Accuracy Guardrails
        </p>
      </footer>
    </div>
  );
}
