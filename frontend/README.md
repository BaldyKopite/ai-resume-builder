# AI Resume Builder - Frontend

The interactive user interface for the AI Resume Builder, built with **Next.js 16 (App Router)**, **React 19**, **TypeScript**, and **Tailwind CSS v4**.

---

## Architecture Overview

```text
src/
├── app/
│   ├── layout.tsx         # Root layout with Geist font definitions & metadata
│   ├── page.tsx           # Multi-step tailoring workflow & side-by-side review UI
│   └── globals.css        # Tailwind v4 utility layers and styling variables
├── services/
│   └── api.ts             # Strongly typed API client with timeout and error mapping
└── types/
    └── resume.ts          # TypeScript interfaces synchronized with backend Pydantic schemas
```

---

## Key Features

1. **Multi-Step Guided Flow**:
   * **Step 1 (Inputs & Job Link)**: Supports job URL scraping (LinkedIn, Seek, generic boards) with graceful paste fallbacks. Accepts PDF/Word resume uploads or plain text.
   * **Step 2 (Side-by-Side Review & Edit)**: Visual diff inspection (`Enhanced Phrasing`, `Position Reordered`, `Keywords Matched`). Editable professional summary, reordered bullet points, and front-loaded ATS skills.
   * **Step 3 (ATS Export Ready)**: Direct downloads for single-column ATS-compliant PDF and Word (.docx) files.
2. **Honesty Guardrails & Gap Analysis**:
   * Displays unmet job requirements in a dedicated panel so candidates can add transferrable experience or add confirmed skills rather than having AI invent claims.
   * Domain-filtered skill pills allowing one-click skill inclusion.
3. **Stateless Privacy by Default**:
   * Operates purely in-memory. Zero local storage or tracking of sensitive candidate data.

---

## Local Development

### Prerequisites
* Node.js 18+ (tested on Node.js 20/24)
* npm or pnpm

### Setup
```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) in your browser.

---

## Environment Variables

Create `.env.local` if you need to point to a custom backend API URL:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Build & Quality Checks

```bash
# Typecheck TypeScript
npx tsc --noEmit

# Production build
npm run build

# Start production server
npm start
```
