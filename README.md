# AI Resume Builder: ATS-Tailored Resume Generator

[![CI / Automated Verification](https://github.com/BaldyKopite/ai-resume-builder/actions/workflows/ci.yml/badge.svg)](https://github.com/BaldyKopite/ai-resume-builder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Django 5.2](https://img.shields.io/badge/Django-5.2-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg?logo=next.js&logoColor=white)](https://nextjs.org/)
[![TypeScript 5](https://img.shields.io/badge/TypeScript-5-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS-v4-38B2AC.svg?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)

A production-ready AI resume tailoring application featuring a **React / Next.js** frontend and a **Python / Django REST Framework** backend.

The application takes a target job posting link (LinkedIn, Seek, or any job board) and a candidate's current resume (PDF, DOCX, or plain text) and generates an ATS-optimized resume tailored to that specific job—backed by a **strict No-Fabrication Rule**, **intelligent skill verification**, and an interactive side-by-side review interface.

---

## Key Features & Invariants

1. **Strict No-Fabrication Engine**:
   - **Zero Hallucination**: Never invents employers, job titles, employment dates, credentials, or metrics.
   - **Gap Analysis**: Any job requirement lacking supporting evidence in the candidate's resume is flagged as an actionable gap in a dedicated notes panel rather than fabricating claims.
   - **Factual Integrity**: Preserves all original metrics (percentages, numbers, dollar amounts, scale figures) verbatim.
2. **Intelligent Skill Recommendation**:
   - Recommends genuine technical and domain skills based on the target job specification.
   - **Domain Filtering**: Excludes non-skills such as mine site locations (*Pilgangoora*, *Colina*), company abbreviations (*PLS*), rosters (*FIFO*, *DIDO*), and conversational syntax (*As*, *Following*, *Operation*).
3. **Casing & Grammatical Integrity**:
   - **Grammar Safeguards**: Weak verbs (e.g., *"Assisted with..."*) are rewritten into natural proactive verbs (*"Collaborated on commissioning..."*).
   - **Selective Casing**: Preserves lower-case common nouns mid-sentence (*operation*, *health*, *troubleshooting*) and only aligns verified technical acronyms (`AHS`, `GNSS`, `OEM`, `OT`) or mixed-case technologies (`MineStar`, `Docker`, `Python`).
4. **Relevance Reordering & ATS Optimization**:
   - Reorders achievement bullets to lead with accomplishments most relevant to the target role.
   - Weaves target job keywords naturally into bullet points where existing candidate history supports the domain.
5. **Multi-Platform Job Scraper with Graceful Fallback**:
   - Scrapes **LinkedIn** (`top-card-layout`, `show-more-less-html`, JSON-LD) and **Seek** (`data-automation="jobAdDetails"`, JSON-LD).
   - If a job board blocks automated access (HTTP 403/429/999, Cloudflare, CAPTCHA, or login wall), the system gracefully prompts the user to paste the job text and continues seamlessly.
6. **Multi-Format Resume Parser**:
   - Extracts structured sections from **PDF** (`pypdf`) and **Word** (`python-docx`).
   - Stitches wrapped multi-line qualifications (e.g., Australian trade certificates and degrees) to prevent specializations from splitting into sub-bullets.
   - Flags incomplete or sparse sections so the candidate knows what information to add.
7. **Interactive Side-by-Side Review Interface**:
   - Built with **React 19 & Next.js 16 (App Router)**.
   - Side-by-side diff view with badges (`Enhanced Phrasing`, `Position Reordered`, `Keywords Matched`).
   - Direct inline editing of summary, skills, and bullet points before export.
8. **ATS-Compliant Document Exporters**:
   - **PDF Export**: ReportLab single-column document with standard fonts and clean typography (no multi-column tables or graphics).
   - **DOCX Export**: Standard Word document formatting with bullet styles and standard margins.
9. **Stateless Privacy-First Architecture**:
   - All resume and job data are processed strictly in-memory and never stored on disk or persisted in a database.

---

## Project Structure

```text
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI test suite (Pytest + Next.js build)
├── backend/
│   ├── config/
│   │   ├── settings.py          # Django & DRF settings, CORS, stateless in-memory DB
│   │   ├── urls.py              # Root API routing
│   │   ├── wsgi.py / asgi.py
│   ├── tailor/
│   │   ├── schemas.py           # Pydantic v2 data models (Job, Resume, Diffs, Gaps)
│   │   ├── views.py             # REST API endpoints (scrape, parse, tailor, export)
│   │   ├── urls.py              # API route definitions (/api/*)
│   │   ├── tests.py             # Automated pytest suite (22 passing tests)
│   │   └── services/
│   │       ├── job_scraper.py   # Scraper with domain keyword & skill filtering
│   │       ├── resume_parser.py # PDF/DOCX parser + multi-line qualification stitching
│   │       ├── tailoring_engine.py # Relevance reordering, casing guardrails, summary synthesis
│   │       └── exporter.py      # ATS-compliant PDF & DOCX generators
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── manage.py
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx       # Root layout with color-scheme metadata
│   │   │   ├── page.tsx         # Review interface & side-by-side diff UI
│   │   │   └── globals.css      # Tailwind CSS v4 design tokens
│   │   ├── services/
│   │   │   └── api.ts           # Typed client API service
│   │   └── types/
│   │       └── resume.ts        # TypeScript interfaces synchronized with backend
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── next.config.ts
├── docker-compose.yml           # One-command full-stack container deployment
├── .gitignore
├── .env.example
├── LICENSE                      # MIT License
└── README.md
```

---

## Quickstart Guide

### Option A: Run with Docker Compose (Recommended)

Run the full stack (backend API + frontend UI) with a single command:

```bash
docker compose up --build
```

- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000/api/health/](http://localhost:8000/api/health/)

---

### Option B: Local Development Setup

#### Prerequisites
- **Python**: 3.10+ (tested on Python 3.12)
- **Node.js**: 18+ (tested on Node.js 20/24)
- **npm** or **pnpm**

#### 1. Backend Setup (Django)

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run automated tests (all 22 tests should pass)
python -m pytest

# Start development server
python manage.py runserver 8000
```

The backend API will be available at `http://127.0.0.1:8000/api/`.

#### 2. Frontend Setup (Next.js)

In a new terminal window:

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The interactive review interface will be live at `http://localhost:3000`.

---

## Exporting & Pushing to GitHub

To push this repository to your GitHub account:

1. Create a new empty repository on [GitHub](https://github.com/new) (e.g. `ai-resume-builder`).
2. Add your GitHub remote and push:

```bash
# Add your GitHub remote repository URL
git remote add origin https://github.com/<YOUR-USERNAME>/<YOUR-REPO-NAME>.git

# Rename branch to main (if desired)
git branch -M main

# Push code to GitHub
git push -u origin main
```

---

## Automated Test Suite

Run the full backend test suite:

```bash
cd backend
python -m pytest -v
```

The test suite covers:
- `test_parse_linkedin_html_structure`: Validates LinkedIn semantic element parsing.
- `test_parse_seek_html_structure`: Validates Seek data-automation parsing.
- `test_scraper_fallback_to_pasted_text_when_url_blocked`: Verifies 403/login wall triggers graceful paste fallback.
- `test_scraper_handles_network_timeout`: Validates timeout handling.
- `test_extract_text_from_pdf` & `test_extract_text_from_docx`: Tests in-memory PDF/DOCX binary extraction.
- `test_parse_resume_handles_sparse_or_unreadable_file`: Verifies sparse section detection.
- `test_parse_resume_rejects_corrupted_file`: Verifies handling of invalid/corrupted files.
- `test_tailoring_engine_preserves_factual_accuracy`: Verifies titles, employers, dates, and metrics stay 100% exact.
- `test_tailoring_engine_reorders_bullets_by_job_relevance`: Validates keyword-based achievement reordering.
- `test_tailoring_engine_flags_gaps_without_fabrication`: Enforces the No-Fabrication Rule for missing skills.
- `test_weak_verb_strengthening_preserves_facts`: Verifies passive-to-active verb rewriting.
- `test_generate_pdf_resume_produces_valid_bytes`: Validates ATS PDF binary generation (`%PDF`).
- `test_generate_docx_resume_produces_valid_bytes`: Validates ATS DOCX OOXML zip archive generation.
- `test_api_*`: Validates all REST API endpoints.
- `test_scraper_does_not_suggest_locations_or_non_skills`: Verifies exclusion of locations, rosters, and common words.
- `test_rewrite_preserves_grammar_and_avoids_awkward_capitalization`: Tests grammar integrity and selective casing.
- `test_resume_parser_stitches_multiline_education`: Validates multi-line qualification stitching.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
