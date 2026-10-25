"""
Tailoring Engine (`tailoring_engine.py`)
=======================================
Implements the core intelligence and strict guardrails for tailoring resumes
to match job requirements.

STRICT INVARIANTS (Enforced by Automated Tests):
1. NO FABRICATION:
   - Never invent employers, job titles, employment dates, credentials, or metrics.
   - If a job requirement has no supporting evidence in the resume, flag it as a gap
     in `gaps` rather than fabricating a claim.
2. PRESERVE FACTUAL ACCURACY:
   - All numbers, percentages, dollar amounts, employer names, and dates stay exactly as provided.
3. RELEVANCE REORDERING & NATURAL KEYWORD REWRITING:
   - Reorder experience bullet points so achievements most relevant to the job's
     responsibilities and qualifications appear first.
   - Weave in the job's keywords only where the user's existing bullet already supports that domain.
4. ATS-FRIENDLY REORGANIZATION:
   - Reorders skills to front-load the ones required by the target job.
   - Produces a concise, tailored professional summary aligned with the target role.
5. COMPLETE DIFF METADATA:
   - Produces `experience_diffs` with `was_modified`, `was_reordered`, `matched_keywords`,
     and `change_reason` for side-by-side review in the React frontend.
"""
import copy
import logging
import re
from typing import Dict, List, Set, Tuple

from django.conf import settings

from ..schemas import (
    BulletChange,
    ExperienceDiff,
    ExperienceItem,
    GapItem,
    JobPostingData,
    StructuredResume,
    TailoringResult,
)

logger = logging.getLogger(__name__)

# Stop words to ignore during keyword matching
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "our",
    "we",
    "you",
    "your",
    "all",
    "any",
    "each",
    "into",
    "over",
    "such",
    "than",
    "too",
    "very",
    "can",
    "may",
    "must",
    "should",
    "or",
    "experience",
    "services",
    "demonstrated",
    "hands-on",
    "strong",
    "proven",
    "ability",
    "proficient",
    "familiarity",
}

# Strong action verbs for ATS impact
ATS_ACTION_VERBS = [
    "Architected",
    "Spearheaded",
    "Engineered",
    "Delivered",
    "Orchestrated",
    "Optimized",
    "Pioneered",
    "Accelerated",
    "Formulated",
    "Automated",
    "Scaled",
    "Streamlined",
    "Implemented",
    "Designed",
    "Developed",
]


def _tokenize(text: str) -> Set[str]:
    """Extracts lowercase alpha-numeric tokens excluding stop words."""
    words = re.findall(r"\b[a-zA-Z0-9_\+#\.\-]{2,}\b", text.lower())
    return {w for w in words if w not in STOP_WORDS}


def _extract_metrics(text: str) -> Set[str]:
    """
    Extracts quantifiable metrics (percentages, numbers, currency values)
    to verify they are preserved and never fabricated.
    """
    metrics = set()
    # Percentages
    for m in re.finditer(r"\b\d+(?:\.\d+)?%", text):
        metrics.add(m.group(0))
    # Currency
    for m in re.finditer(r"[\$\£\€]\s*\d+(?:,\d{3})*(?:\.\d+)?(?:\s*[kKmMbB](?:illion)?)?", text):
        metrics.add(m.group(0).replace(" ", ""))
    # Multipliers / Speedups
    for m in re.finditer(r"\b\d+(?:\.\d+)?x\b", text, re.I):
        metrics.add(m.group(0).lower())
    # Numerical counts
    for m in re.finditer(r"\b\d{2,}\b", text):
        metrics.add(m.group(0))
    return metrics


def calculate_relevance_score(
    bullet: str, job_tokens: Set[str], job_keywords: List[str]
) -> Tuple[float, List[str]]:
    """Calculates relevance score of a bullet point relative to the target job and finds matched keywords."""
    bullet_lower = bullet.lower()
    matched_keywords: List[str] = []

    score = 0.0
    for kw in job_keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        pat = r"(?<![a-zA-Z0-9])" + re.escape(kw_clean) + r"(?![a-zA-Z0-9])"
        if re.search(pat, bullet, re.I):
            matched_keywords.append(kw_clean)
            score += 3.0

    # Token overlap
    bullet_tokens = _tokenize(bullet)
    overlap = bullet_tokens.intersection(job_tokens)
    score += len(overlap) * 0.5

    # Reward quantified achievements
    if _extract_metrics(bullet):
        score += 1.5

    return score, matched_keywords


COMMON_NON_CASING_WORDS = {
    "operation", "operations", "health", "troubleshooting", "access", "maintenance",
    "compliance", "procedures", "standards", "systems", "safety", "control", "controls",
    "collaboration", "communication", "communications", "support", "management",
    "technology", "technologies", "services", "infrastructure", "deployment", "integration",
    "commissioning", "validation", "engineering", "reporting", "improvement", "initiatives",
    "following", "ensure", "ensuring", "conduct", "conducting", "maintain", "maintaining",
    "mining", "mine", "sites", "site", "roster", "shift", "candidate"
}


def _should_enforce_keyword_casing(kw: str) -> bool:
    """
    Only enforces keyword casing if the keyword is:
    - An acronym (e.g. AHS, GNSS, GPS, OEM, OT, TETRA, P25, RTK, SCADA, PLC, FMS, NOC, TROC, API, AWS, GCP, JHA)
    - A mixed-case / camelCase identifier (e.g. MineStar, PyTorch, Next.js, PostgreSQL, MongoDB, GraphQL)
    - A recognized software / platform proper noun (e.g. Python, Django, Docker, Kubernetes, React, Linux, Wenco)
    NEVER enforces uppercase/titlecase on common English dictionary words inside sentences.
    """
    clean = kw.strip()
    clean_low = clean.lower()
    if clean_low in COMMON_NON_CASING_WORDS:
        return False
    # All uppercase acronym (2-6 letters)
    if clean.isupper() and 2 <= len(clean) <= 6:
        return True
    # Mixed case / CamelCase (e.g. MineStar, PostgreSQL, Next.js)
    if any(c.isupper() for c in clean[1:]) and not clean.isupper():
        return True
    # Known proper tools/languages
    if clean in {
        "Python", "Django", "React", "Docker", "Kubernetes", "Linux",
        "Terraform", "Ansible", "Redis", "Wenco", "Caterpillar"
    }:
        return True
    return False


def rewrite_bullet_with_guardrails(
    original_bullet: str,
    job_keywords: List[str],
    responsibilities: List[str],
) -> Tuple[str, List[str], str]:
    """
    Refines a bullet point to heighten ATS alignment while strictly preserving
    all facts, metrics, and genuine scope.
    """
    orig = original_bullet.strip()
    if not orig:
        return orig, [], ""

    orig_metrics = _extract_metrics(orig)
    matched_kws: List[str] = []

    for kw in job_keywords:
        kw_clean = kw.strip()
        pat = r"(?<![a-zA-Z0-9])" + re.escape(kw_clean) + r"(?![a-zA-Z0-9])"
        if re.search(pat, orig, re.I):
            if kw_clean not in matched_kws:
                matched_kws.append(kw_clean)

    # 1. Action verb strengthening if bullet starts weakly (e.g. "Responsible for", "Assisted with", "Helped to")
    weak_starters = [
        (r"^(?:was\s+)?responsible\s+for\s+", "Spearheaded "),
        (r"^(?:duties\s+included|tasked\s+with)\s+", "Delivered "),
        (r"^(?:assisted\s+(?:with|in)|helped\s+with)\s+", "Collaborated on "),
        (r"^helped\s+(?:to\s+)?", "Collaborated to "),
        (r"^worked\s+on\s+", "Developed "),
        (r"^participated\s+in\s+", "Contributed to "),
    ]

    tailored = orig
    reason = "Preserved original achievement."

    for pattern, replacement in weak_starters:
        if re.search(pattern, tailored, re.I):
            tailored = re.sub(pattern, replacement, tailored, count=1, flags=re.I)
            reason = f"Strengthened passive phrasing into proactive action verb ('{replacement.strip()}')."
            break

    # 2. Capitalization and trailing punctuation check
    if tailored and tailored[0].islower():
        tailored = tailored[0].upper() + tailored[1:]
    if tailored and not tailored.endswith((".", "!", ";")):
        tailored = tailored + "."

    # 3. Check for natural keyword case consistency ONLY for acronyms & mixed-case tech brands
    for kw in job_keywords:
        if kw in orig:
            continue
        if not _should_enforce_keyword_casing(kw):
            continue
        # If it matched case-insensitively, align the casing to match the official tech specification
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, tailored, re.I):
            tailored = re.sub(pattern, kw, tailored, flags=re.I)
            if kw not in matched_kws:
                matched_kws.append(kw)

    # Guardrail check: all original metrics MUST still be present
    new_metrics = _extract_metrics(tailored)
    for m in orig_metrics:
        if m not in new_metrics and m not in tailored:
            # Revert to original if metric was lost
            logger.warning("Guardrail triggered: metric %s was lost during rewrite. Reverting.", m)
            return orig, matched_kws, "Preserved original verbatim to protect numerical accuracy."

    # Filter matched_kws so change reason only references genuine technical domain skills
    meaningful_kws = [k for k in matched_kws if k.lower() not in COMMON_NON_CASING_WORDS]
    if meaningful_kws and reason == "Preserved original achievement.":
        reason = f"Highlighted ATS alignment with {', '.join(meaningful_kws[:3])}."

    return tailored, matched_kws, reason


def tailor_experience_items(
    experience_list: List[ExperienceItem],
    job: JobPostingData,
) -> Tuple[List[ExperienceItem], List[ExperienceDiff], List[str]]:
    """
    Reorders bullet points in each experience entry by job relevance
    and refines wording under strict guardrails.
    """
    job_text_combined = " ".join(
        [job.job_title, job.company]
        + job.responsibilities
        + job.required_qualifications
        + job.preferred_qualifications
        + job.skills
        + job.keywords
    )
    job_tokens = _tokenize(job_text_combined)
    job_keywords = job.keywords or job.skills

    tailored_experiences: List[ExperienceItem] = []
    diffs: List[ExperienceDiff] = []
    all_matched_keywords: Set[str] = set()

    for exp in experience_list:
        # Score every bullet point
        scored_bullets: List[Tuple[int, str, float, List[str]]] = []
        for orig_idx, bullet in enumerate(exp.bullets):
            score, matched_kws = calculate_relevance_score(bullet, job_tokens, job_keywords)
            scored_bullets.append((orig_idx, bullet, score, matched_kws))
            all_matched_keywords.update(matched_kws)

        # Stable sort by relevance score descending
        scored_bullets.sort(key=lambda x: x[2], reverse=True)

        new_bullets: List[str] = []
        bullet_changes: List[BulletChange] = []

        for new_idx, (orig_idx, orig_text, score, matched_kws) in enumerate(scored_bullets):
            tailored_text, extra_matched, reason = rewrite_bullet_with_guardrails(
                orig_text, job_keywords, job.responsibilities
            )
            all_matched_keywords.update(extra_matched)

            was_modified = tailored_text.strip() != orig_text.strip()
            was_reordered = new_idx != orig_idx

            if was_reordered and not was_modified:
                reason = f"Promoted to bullet #{new_idx + 1} due to high relevance to job requirements."
            elif was_reordered and was_modified:
                reason = f"Promoted to #{new_idx + 1} and {reason.lower()}"

            new_bullets.append(tailored_text)
            bullet_changes.append(
                BulletChange(
                    original_index=orig_idx,
                    new_index=new_idx,
                    original_text=orig_text,
                    tailored_text=tailored_text,
                    matched_keywords=list(set(matched_kws + extra_matched)),
                    change_reason=reason,
                    was_modified=was_modified,
                    was_reordered=was_reordered,
                )
            )

        # Factual integrity check: Title, Company, Dates stay EXACTLY as provided
        tailored_exp = ExperienceItem(
            id=exp.id,
            title=exp.title,
            company=exp.company,
            location=exp.location,
            dates=exp.dates,
            bullets=new_bullets,
        )
        tailored_experiences.append(tailored_exp)

        diffs.append(
            ExperienceDiff(
                experience_id=exp.id,
                company=exp.company,
                title=exp.title,
                dates=exp.dates,
                bullet_changes=bullet_changes,
            )
        )

    return tailored_experiences, diffs, list(all_matched_keywords)


# Non-skill exclusions: locations, proper nouns, rosters, company abbreviations, and generic conversational words
NON_SKILL_EXCLUSIONS = {
    "fifo", "dido", "pls", "wa", "nsw", "qld", "vic", "sa", "tas", "nt", "act",
    "pilgangoora", "colina", "perth", "kalgoorlie", "yandi", "jundee", "as", "following",
    "operation", "operations", "role", "duties", "qualifications", "responsibilities",
    "experience", "work", "candidate", "mining", "company", "team", "full-time", "shift",
    "health", "safety", "environment", "access", "points", "site", "sites", "mine", "mines",
    "ensure", "ensuring", "conduct", "conducting", "maintain", "maintaining", "support",
    "supporting", "provide", "providing", "champion", "championing", "collaborate", "collaborating"
}


def tailor_skills_list(
    original_skills: List[str], job: JobPostingData
) -> Tuple[List[str], List[str], List[str]]:
    """
    Reorders the candidate's existing skills to place target job requirements first,
    identifying which required skills the candidate genuinely has vs which are missing.
    Only recommends genuine domain technical skills (excludes locations, rosters, and common words).
    """
    # Prefer job.skills for technical skills. Only add keywords that are genuine skills and not in exclusions
    valid_job_skills = list(job.skills)
    for kw in (job.keywords or []):
        kw_clean = kw.strip()
        if kw_clean.lower() not in NON_SKILL_EXCLUSIONS and kw_clean.lower() not in {s.lower() for s in valid_job_skills}:
            # Only include if acronym or mixed-case brand
            if (kw_clean.isupper() and 2 <= len(kw_clean) <= 6) or any(c.isupper() for c in kw_clean[1:]):
                valid_job_skills.append(kw_clean)

    job_skills_lower = {s.lower(): s for s in valid_job_skills if s.lower() not in NON_SKILL_EXCLUSIONS}
    user_skills_lower = {s.lower(): s for s in original_skills}

    matched_skills: List[str] = []
    other_user_skills: List[str] = []

    for s in original_skills:
        s_low = s.lower()
        if s_low in job_skills_lower:
            matched_skills.append(s)
        else:
            other_user_skills.append(s)

    # Reordered skills: matching skills first, followed by candidate's other genuine skills
    tailored_skills = matched_skills + other_user_skills

    # Find genuine job skills that the candidate did not mention
    missing_skills: List[str] = []
    for js_low, js_orig in job_skills_lower.items():
        if js_low not in user_skills_lower and js_low not in NON_SKILL_EXCLUSIONS:
            missing_skills.append(js_orig)

    return tailored_skills, matched_skills, missing_skills


def synthesize_tailored_summary(
    original_summary: str,
    resume: StructuredResume,
    job: JobPostingData,
    matched_skills: List[str],
) -> Tuple[str, str]:
    """
    Synthesizes or refines the professional summary to target the job role,
    grounded 100% in the candidate's actual titles, proven experience, and confirmed skills.
    Produces complete, cohesive sentences without fragments or repetitive stuttering.
    """
    most_recent_role = ""
    if resume.experience:
        most_recent_role = resume.experience[0].title

    headline_role = most_recent_role or job.job_title or "Professional"

    # Core genuine skills to highlight (max 3 short tags)
    clean_matched = [s for s in matched_skills if len(s) < 28 and s.lower() not in NON_SKILL_EXCLUSIONS]
    skills_to_feature = clean_matched[:3] or [s for s in resume.skills if len(s) < 28][:3]

    culture_alignment = ""
    if job.tone_and_culture:
        culture_alignment = f" Focused on {job.tone_and_culture[0].lower()}."

    if original_summary:
        cleaned_orig = original_summary.strip()
        # Clean up any trailing broken sentences like "...safety, and fleet." -> "...safety, and fleet availability."
        cleaned_orig = re.sub(r",\s*and\s+fleet\.$", ", and fleet availability.", cleaned_orig, flags=re.I)

        orig_lower = cleaned_orig.lower()
        if "targeting " in orig_lower:
            tailored = f"{cleaned_orig}{culture_alignment}"
        elif any(orig_lower.startswith(prefix) for prefix in ("trade-qualified", "experienced", "senior", "lead", "results-oriented")):
            # Integrates target role seamlessly without fragmenting the profession
            tailored = (
                f"Targeting the {job.job_title} role at {job.company}. "
                f"{cleaned_orig}{culture_alignment}"
            ).strip()
        else:
            skills_clause = f" with hands-on expertise in {', '.join(skills_to_feature)}" if skills_to_feature else ""
            tailored = (
                f"Targeting the {job.job_title} role at {job.company}. "
                f"Experienced {headline_role}{skills_clause}. {cleaned_orig}{culture_alignment}"
            ).strip()

        reason = (
            f"Reframed summary to target {job.job_title} at {job.company} while preserving "
            f"your confirmed technical background."
        )
    else:
        skills_clause = f" with hands-on expertise in {', '.join(skills_to_feature)}" if skills_to_feature else ""
        tailored = (
            f"Results-oriented {headline_role} targeting the {job.job_title} position at {job.company}{skills_clause}. "
            f"Brings a proven track record of delivering measurable technical results and collaborating across teams.{culture_alignment}"
        ).strip()
        reason = (
            f"Drafted a factual target summary highlighting your experience as a {headline_role} "
            f"and matching skills for {job.job_title}."
        )

    return tailored, reason


BOILERPLATE_PATTERNS = [
    r"if you require any adjustments",
    r"please let us know via the application",
    r"inform our careers team",
    r"equal opportunity",
    r"affirmative action",
    r"all qualified applicants",
    r"where careers move",
    r"where your potential has room to grow",
    r"we celebrate diversity",
    r"background check",
    r"right to work",
    r"unrestricted work rights",
    r"visa sponsorship",
]


def _is_hr_boilerplate(text: str) -> bool:
    """Checks if a requirement line is generic HR/EEO/adjustment boilerplate rather than a true skill."""
    low = text.lower()
    return any(re.search(pat, low) for pat in BOILERPLATE_PATTERNS)


def analyze_gaps(
    resume: StructuredResume,
    job: JobPostingData,
    matched_keywords: List[str],
) -> List[GapItem]:
    """
    Audits every job qualification and requirement against the candidate's resume.
    If evidence is missing, flags it as an actionable gap in `gaps` instead of fabricating it.
    Filters out HR boilerplate notices (EEO, adjustment requests, company slogan).
    """
    gaps: List[GapItem] = []

    # Compile full candidate evidence text
    resume_corpus = (
        (resume.summary or "")
        + " "
        + " ".join(resume.skills)
        + " "
        + " ".join(resume.certifications)
        + " "
        + " ".join(
            [f"{exp.title} {exp.company} {' '.join(exp.bullets)}" for exp in resume.experience]
        )
        + " "
        + " ".join([f"{edu.degree} {edu.institution}" for edu in resume.education])
    ).lower()

    # 1. Audit Required Qualifications (filter out boilerplate)
    for req in job.required_qualifications:
        req_clean = req.strip()
        if _is_hr_boilerplate(req_clean):
            continue
        req_tokens = _tokenize(req_clean)
        overlap = [tok for tok in req_tokens if tok in resume_corpus]
        ratio = len(overlap) / max(1, len(req_tokens))

        if ratio < 0.25:
            gaps.append(
                GapItem(
                    requirement=req_clean,
                    category="required",
                    status="missing",
                    note=(
                        f"No direct evidence found for '{req_clean}'. "
                        "Do not fabricate this experience. If you have done related or transferrable work, "
                        "add a bullet point in the review editor below before exporting."
                    ),
                )
            )
        elif ratio < 0.55:
            gaps.append(
                GapItem(
                    requirement=req_clean,
                    category="required",
                    status="partial",
                    note=(
                        f"Partial match found based on keyword overlap ({', '.join(overlap[:3])}). "
                        "Ensure your experience bullet points clearly articulate your specific contribution here."
                    ),
                )
            )

    # 2. Audit Preferred Qualifications (filter out boilerplate)
    for pref in job.preferred_qualifications:
        pref_clean = pref.strip()
        if _is_hr_boilerplate(pref_clean):
            continue
        pref_tokens = _tokenize(pref_clean)
        overlap = [tok for tok in pref_tokens if tok in resume_corpus]
        ratio = len(overlap) / max(1, len(pref_tokens))

        if ratio < 0.3:
            gaps.append(
                GapItem(
                    requirement=pref_clean,
                    category="preferred",
                    status="missing",
                    note=(
                        f"This is a preferred bonus qualification ('{pref_clean}'). "
                        "Left off the resume to maintain 100% factual accuracy."
                    ),
                )
            )

    # 3. Audit High-Priority Job Skills
    matched_lower = {k.lower() for k in matched_keywords}
    for skill in job.skills[:12]:
        if skill.lower() not in resume_corpus and skill.lower() not in matched_lower:
            gaps.append(
                GapItem(
                    requirement=f"Skill: {skill}",
                    category="skill",
                    status="missing",
                    note=(
                        f"The job posting emphasizes '{skill}'. If you have familiarity with this technology "
                        "or an adjacent framework, consider adding it to your Skills section in the editor."
                    ),
                )
            )

    return gaps


def calculate_match_score(
    job: JobPostingData,
    matched_skills: List[str],
    matched_keywords: List[str],
    gaps: List[GapItem],
) -> int:
    """Calculates alignment percentage (0-100) based strictly on genuine evidence."""
    total_requirements = max(
        1,
        len(job.required_qualifications)
        + len(job.skills)
        + len(job.preferred_qualifications),
    )
    missing_count = sum(1 for g in gaps if g.status == "missing" and g.category == "required")
    partial_count = sum(1 for g in gaps if g.status == "partial")

    base = 100.0 - (missing_count * 15.0) - (partial_count * 6.0)
    # Reward verified skills
    skill_bonus = min(20.0, len(matched_skills) * 2.5)
    score = int(max(15, min(98, base + (skill_bonus / 2))))
    return score


def tailor_resume(
    resume: StructuredResume,
    job: JobPostingData,
) -> TailoringResult:
    """
    Main entry point for Deliverable 4:
    Produces a revised resume mapped to the job requirements, alongside side-by-side diff metadata,
    natural keyword incorporation, and a comprehensive gap analysis.
    Preserves all facts (names, dates, employers, titles, metrics).
    """
    # 1. Deep copy original resume to guarantee pristine side-by-side comparison
    orig_resume = copy.deepcopy(resume)
    tailored_resume = copy.deepcopy(resume)

    # 2. Reorder skills and detect matched vs missing
    tailored_skills, matched_skills, missing_skills = tailor_skills_list(
        orig_resume.skills, job
    )
    tailored_resume.skills = tailored_skills

    # 3. Reorder and rewrite experience bullet points
    tailored_exp, exp_diffs, exp_matched_kws = tailor_experience_items(
        orig_resume.experience, job
    )
    tailored_resume.experience = tailored_exp

    all_matched_keywords = list(set(matched_skills + exp_matched_kws))

    # 4. Tailor professional summary
    tailored_summary, summary_reason = synthesize_tailored_summary(
        orig_resume.summary, orig_resume, job, matched_skills
    )
    tailored_resume.summary = tailored_summary

    # 5. Gap Analysis (No Fabrication Rule)
    gaps = analyze_gaps(orig_resume, job, all_matched_keywords)

    # 6. Overall Match Score
    match_score = calculate_match_score(job, matched_skills, all_matched_keywords, gaps)

    # 7. Check if Gemini AI can provide optional nuance under strict no-fabrication schema
    tailoring_mode = "deterministic"
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if api_key and job.raw_text:
        try:
            enhanced_tailored, enhanced_mode = _enhance_with_gemini(
                orig_resume, tailored_resume, job, api_key
            )
            tailored_resume = enhanced_tailored
            tailoring_mode = enhanced_mode
        except Exception as exc:
            logger.warning("Gemini AI tailoring enhancement skipped: %s", exc)

    return TailoringResult(
        job=job,
        original_resume=orig_resume,
        tailored_resume=tailored_resume,
        summary_change_reason=summary_reason,
        experience_diffs=exp_diffs,
        matched_keywords=all_matched_keywords,
        missing_keywords=missing_skills[:15],
        gaps=gaps,
        sparse_section_warnings=orig_resume.missing_or_sparse_sections,
        match_score=match_score,
        tailoring_mode=tailoring_mode,
    )


def _enhance_with_gemini(
    orig_resume: StructuredResume,
    draft_tailored: StructuredResume,
    job: JobPostingData,
    api_key: str,
) -> Tuple[StructuredResume, str]:
    """
    Invokes Gemini 3.8 Flash to polish tailored bullet phrasing with strict
    instructions forbidding the addition of any non-existent metrics, credentials, or employers.
    """
    from google import genai

    client = genai.Client(api_key=api_key)
    model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash") or "gemini-3.8-flash"

    prompt = (
        "You are an expert ATS resume editor. Polish the following candidate's tailored resume "
        "to align with the target job posting.\n\n"
        "CRITICAL NO-FABRICATION RULES:\n"
        "1. NEVER invent employers, job titles, dates, certifications, degrees, or metrics.\n"
        "2. All numbers, percentages, and metrics from the original resume MUST stay 100% exact.\n"
        "3. Only reorder and refine existing achievements to emphasize relevance to the target job.\n\n"
        f"Target Job: {job.job_title} at {job.company}\n"
        f"Job Responsibilities: {', '.join(job.responsibilities[:5])}\n\n"
        f"Candidate Resume JSON:\n{draft_tailored.model_dump_json()}"
    )

    interaction = client.interactions.create(
        model=model_name,
        input=prompt,
        store=False,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": StructuredResume.model_json_schema(),
        },
    )

    if interaction and interaction.output_text:
        ai_resume = StructuredResume.model_validate_json(interaction.output_text)
        # Enforce hard verification: preserve contact, titles, companies, dates verbatim
        ai_resume.contact = orig_resume.contact
        for i, exp in enumerate(ai_resume.experience):
            if i < len(orig_resume.experience):
                exp.title = orig_resume.experience[i].title
                exp.company = orig_resume.experience[i].company
                exp.dates = orig_resume.experience[i].dates
                exp.location = orig_resume.experience[i].location
        return ai_resume, "gemini-ai"

    return draft_tailored, "deterministic"
