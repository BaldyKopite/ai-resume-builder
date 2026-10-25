"""
Job Posting Scraper & Parser (`job_scraper.py`)
===============================================
Fetches job postings from LinkedIn, Seek, or generic job board URLs,
extracts structured job information (title, company, responsibilities,
required/preferred qualifications, skills, keywords, and tone/culture signals),
and enforces graceful fallback to pasted text when sites block automated scraping,
require login walls, or return unreadable pages.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

from ..schemas import JobPostingData

logger = logging.getLogger(__name__)


class JobScrapeError(Exception):
    """
    Raised when a job URL cannot be fetched or parsed (e.g. HTTP 403/429/999,
    login wall, CAPTCHA, timeout, or empty content), signaling the frontend
    to prompt the user to paste the job description text instead.
    """

    def __init__(
        self,
        message: str,
        code: str = "JOB_URL_UNFETCHABLE",
        requires_paste_fallback: bool = True,
        source_url: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.requires_paste_fallback = requires_paste_fallback
        self.source_url = source_url


# Comprehensive curated tech, business, and domain skill dictionary for deterministic extraction
KNOWN_SKILLS_AND_KEYWORDS = [
    # Programming Languages
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "C#",
    "C++",
    "Go",
    "Golang",
    "Rust",
    "Ruby",
    "PHP",
    "Swift",
    "Kotlin",
    "SQL",
    "NoSQL",
    "R",
    "Scala",
    "Bash",
    "Shell",
    "HTML",
    "CSS",
    # Frontend & Web
    "React",
    "Next.js",
    "Vue.js",
    "Angular",
    "Svelte",
    "Tailwind CSS",
    "Redux",
    "GraphQL",
    "REST API",
    "RESTful APIs",
    "WebSockets",
    "Accessibility",
    "WCAG",
    "Webpack",
    "Vite",
    # Backend & Frameworks
    "Django",
    "Django REST Framework",
    "DRF",
    "FastAPI",
    "Flask",
    "Node.js",
    "Express",
    "Spring Boot",
    ".NET",
    "ASP.NET",
    "Microservices",
    "gRPC",
    "Celery",
    "RabbitMQ",
    "Kafka",
    # Data & Databases
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "DynamoDB",
    "Snowflake",
    "BigQuery",
    "Redshift",
    "Apache Spark",
    "Airflow",
    "dbt",
    "Pandas",
    "NumPy",
    "ETL",
    "Data Modeling",
    "Data Warehousing",
    "Tableau",
    "Power BI",
    # Cloud, DevOps & Infrastructure
    "AWS",
    "Amazon Web Services",
    "GCP",
    "Google Cloud",
    "Azure",
    "Docker",
    "Kubernetes",
    "Terraform",
    "Ansible",
    "CI/CD",
    "GitHub Actions",
    "GitLab CI",
    "Jenkins",
    "Linux",
    "Nginx",
    "Prometheus",
    "Grafana",
    "Datadog",
    "Serverless",
    "Lambda",
    # AI & Machine Learning
    "Machine Learning",
    "Deep Learning",
    "NLP",
    "Natural Language Processing",
    "LLM",
    "Large Language Models",
    "Generative AI",
    "PyTorch",
    "TensorFlow",
    "Scikit-learn",
    "RAG",
    "Prompt Engineering",
    "Computer Vision",
    "MLOps",
    # Engineering Practices, Security & Product
    "Agile",
    "Scrum",
    "Kanban",
    "TDD",
    "Test-Driven Development",
    "Unit Testing",
    "Automated Testing",
    "Pytest",
    "Jest",
    "Playwright",
    "Cypress",
    "System Design",
    "Distributed Systems",
    "Scalability",
    "High Availability",
    "Performance Optimization",
    "Security",
    "OAuth",
    "JWT",
    "SOC2",
    "GDPR",
    "Code Review",
    "Mentoring",
    "Cross-functional Collaboration",
    "Stakeholder Management",
    "Product Management",
    "Roadmap Planning",
    "A/B Testing",
    "Customer Obsession",
    "Project Management",
    # Operational Technology, Autonomous Haulage, Fleet & Industrial Systems
    "Autonomous Haulage",
    "Autonomous Haulage Systems",
    "AHS",
    "Autonomous Operating Zone",
    "AOZ",
    "Caterpillar MineStar",
    "MineStar Command",
    "MineStar Fleet",
    "MineStar Terrain",
    "CAT Command",
    "Wenco",
    "Fleet Management Systems",
    "FMS",
    "Machine Guidance",
    "Machine Control",
    "GNSS",
    "GPS",
    "RTK",
    "Radio Telemetry",
    "Telemetry",
    "Two-Way Radio",
    "TETRA",
    "P25",
    "DMR",
    "Microwave",
    "Leaky Feeder",
    "Operational Technology",
    "OT",
    "SCADA",
    "PLC",
    "NOC",
    "TROC",
    "Critical Controls",
    "JHA",
    "Take 5",
    "OEM",
    "Preventative Maintenance",
    "Commissioning",
    "Fault Finding",
    "Troubleshooting",
]

CULTURE_SIGNALS_MAP = {
    "Fast-paced & high-ownership": [
        r"\bfast[- ]paced\b",
        r"\bhigh[- ]growth\b",
        r"\bautonomous\b",
        r"\bownership\b",
        r"\bself[- ]starter\b",
        r"\bambiguity\b",
        r"\bstartup\b",
    ],
    "Collaborative & cross-functional": [
        r"\bcross[- ]functional\b",
        r"\bcollaborat(?:e|ive|ion)\b",
        r"\bteam[- ]player\b",
        r"\bempathetic\b",
        r"\bopen communication\b",
        r"\binclusive\b",
        r"\bmentorship\b",
        r"\bpair programming\b",
    ],
    "Engineering excellence & rigor": [
        r"\bproduction[- ]ready\b",
        r"\bhigh[- ]quality\b",
        r"\bbest practices\b",
        r"\bclean code\b",
        r"\btest[- ]driven\b",
        r"\breliability\b",
        r"\bcraftsmanship\b",
        r"\bmission[- ]critical\b",
    ],
    "Customer-centric & impact-driven": [
        r"\bcustomer[- ]centric\b",
        r"\bcustomer[- ]obsessed\b",
        r"\buser[- ]focused\b",
        r"\bimpact[- ]driven\b",
        r"\bdata[- ]driven\b",
        r"\bmeasurable outcomes\b",
    ],
    "Flexible & remote-friendly": [
        r"\bremote[- ]first\b",
        r"\bhybrid\b",
        r"\bflexible hours\b",
        r"\bwork[- ]life balance\b",
        r"\basync\b",
    ],
}

LOGIN_WALL_PATTERNS = [
    r"authwall",
    r"sign in to view",
    r"join linkedin",
    r"log in to continue",
    r"please verify you are a human",
    r"access denied",
    r"enable javascript and cookies to continue",
    r"cloudflare",
    r"captcha",
]


def detect_source_site(url: str) -> str:
    """Identifies the job board platform from the URL hostname."""
    if not url:
        return "text"
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or "").lower()
        if "linkedin.com" in host:
            return "linkedin"
        if "seek.com" in host or "seek.co.nz" in host:
            return "seek"
        return "generic"
    except Exception:
        return "generic"


def validate_url(url: str) -> str:
    """Validates URL format and scheme."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise JobScrapeError(
            "No job URL was provided. Please provide a valid job URL or paste the job description text.",
            code="EMPTY_JOB_URL",
        )
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise JobScrapeError(
            f"Invalid URL format '{cleaned}'. Please enter a complete http/https URL or paste the job description text directly.",
            code="INVALID_JOB_URL",
            source_url=cleaned,
        )
    # Block local/loopback SSRF in production unless explicitly testing
    hostname = (parsed.hostname or "").lower()
    if hostname in ("169.254.169.254", "metadata.google.internal"):
        raise JobScrapeError(
            "URL host is not permitted. Please paste the job description text instead.",
            code="BLOCKED_HOST",
            source_url=cleaned,
        )
    return cleaned


def fetch_job_html(url: str, timeout: int = 10) -> str:
    """
    Fetches raw HTML from a job posting URL with browser-like headers.
    Raises JobScrapeError on network failure, bot block (403/429/999), or login wall.
    """
    validated_url = validate_url(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        response = requests.get(
            validated_url, headers=headers, timeout=timeout, allow_redirects=True
        )
    except requests.exceptions.Timeout as exc:
        raise JobScrapeError(
            "Timed out while fetching the job link. Many job boards throttle automated requests—please paste the job description text below to continue.",
            code="JOB_FETCH_TIMEOUT",
            source_url=validated_url,
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise JobScrapeError(
            f"Could not connect to the job link ({exc.__class__.__name__}). Please paste the job description text instead.",
            code="JOB_FETCH_NETWORK_ERROR",
            source_url=validated_url,
        ) from exc

    # Check final URL for LinkedIn authwall redirect
    final_url = (response.url or "").lower()
    if "authwall" in final_url or "/login" in final_url or "uas/login" in final_url:
        raise JobScrapeError(
            "This job board redirected to a sign-in wall. Please copy and paste the job description text directly so we can continue.",
            code="JOB_AUTHWALL_REDIRECT",
            source_url=validated_url,
        )

    if response.status_code in (401, 403, 429, 999):
        raise JobScrapeError(
            f"The job site blocked automated access (HTTP {response.status_code}). Please paste the job description text below to continue.",
            code="JOB_SITE_BLOCKED",
            source_url=validated_url,
        )

    if response.status_code >= 400:
        raise JobScrapeError(
            f"The job link returned HTTP {response.status_code}. Please paste the job description text instead.",
            code="JOB_HTTP_ERROR",
            source_url=validated_url,
        )

    html = response.text or ""
    if len(html.strip()) < 100:
        raise JobScrapeError(
            "The job page returned empty or unreadable content. Please paste the job description text directly.",
            code="JOB_EMPTY_RESPONSE",
            source_url=validated_url,
        )

    return html


def _extract_json_ld_job_posting(soup: BeautifulSoup) -> Dict[str, str]:
    """Extracts Schema.org JobPosting metadata if present in JSON-LD script tags."""
    result: Dict[str, str] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            # Also check @graph
            graph = item.get("@graph")
            if isinstance(graph, list):
                items.extend([g for g in graph if isinstance(g, dict)])
            if item.get("@type") == "JobPosting":
                result["title"] = str(item.get("title") or "")
                org = item.get("hiringOrganization")
                if isinstance(org, dict):
                    result["company"] = str(org.get("name") or "")
                loc = item.get("jobLocation")
                if isinstance(loc, dict):
                    addr = loc.get("address")
                    if isinstance(addr, dict):
                        parts = [
                            addr.get("addressLocality", ""),
                            addr.get("addressRegion", ""),
                            addr.get("addressCountry", ""),
                        ]
                        result["location"] = ", ".join([p for p in parts if p])
                desc_html = item.get("description") or ""
                if desc_html:
                    desc_soup = BeautifulSoup(desc_html, "html.parser")
                    result["description"] = desc_soup.get_text(separator="\n", strip=True)
                return result
    return result


def parse_linkedin_html(soup: BeautifulSoup) -> Tuple[str, str, str, str]:
    """
    Extracts (job_title, company, location, description_text) from LinkedIn job HTML structures.
    Supports both guest view (`top-card-layout__*`, `show-more-less-html__markup`) and JSON-LD.
    """
    json_ld = _extract_json_ld_job_posting(soup)

    title_el = (
        soup.select_one("h1.top-card-layout__title")
        or soup.select_one("h1.topcard__title")
        or soup.select_one("h1.job-details-jobs-unified-top-card__job-title")
        or soup.find("h1")
    )
    company_el = (
        soup.select_one("a.topcard__org-name-link")
        or soup.select_one("span.topcard__flavor")
        or soup.select_one(".job-details-jobs-unified-top-card__company-name")
        or soup.select_one("[data-tracking-control-name='public_jobs_topcard-org-name']")
    )
    location_el = (
        soup.select_one("span.topcard__flavor--bullet")
        or soup.select_one(".top-card-layout__second-subline span")
    )
    desc_el = (
        soup.select_one("div.show-more-less-html__markup")
        or soup.select_one("div.description__text")
        or soup.select_one("section.show-more-less-html")
        or soup.select_one("#job-details")
    )

    title = (title_el.get_text(strip=True) if title_el else "") or json_ld.get("title", "")
    company = (company_el.get_text(strip=True) if company_el else "") or json_ld.get("company", "")
    location = (location_el.get_text(strip=True) if location_el else "") or json_ld.get(
        "location", ""
    )

    if desc_el:
        for li in desc_el.find_all("li"):
            li.insert_before("\n- ")
        for br in desc_el.find_all(["br", "p", "h2", "h3", "h4", "strong"]):
            br.insert_before("\n")
        description = desc_el.get_text(separator=" ", strip=True)
        description = re.sub(r"[ \t]+", " ", description)
    else:
        description = json_ld.get("description", "")

    return title, company, location, description


def parse_seek_html(soup: BeautifulSoup) -> Tuple[str, str, str, str]:
    """
    Extracts (job_title, company, location, description_text) from Seek job HTML structures.
    Supports Seek's `data-automation` attributes (`job-detail-title`, `advertiser-name`, `jobAdDetails`) and JSON-LD.
    """
    json_ld = _extract_json_ld_job_posting(soup)

    title_el = (
        soup.select_one("[data-automation='job-detail-title']")
        or soup.select_one("h1[data-automation]")
        or soup.find("h1")
    )
    company_el = (
        soup.select_one("[data-automation='advertiser-name']")
        or soup.select_one("[data-automation='job-header-company-name']")
    )
    location_el = (
        soup.select_one("[data-automation='job-detail-location']")
        or soup.select_one("[data-automation='job-location']")
    )
    desc_el = (
        soup.select_one("[data-automation='jobAdDetails']")
        or soup.select_one("[data-automation='jobDescription']")
        or soup.select_one("div[data-automation='job-description']")
    )

    title = (title_el.get_text(strip=True) if title_el else "") or json_ld.get("title", "")
    company = (company_el.get_text(strip=True) if company_el else "") or json_ld.get("company", "")
    location = (location_el.get_text(strip=True) if location_el else "") or json_ld.get(
        "location", ""
    )

    if desc_el:
        for li in desc_el.find_all("li"):
            li.insert_before("\n- ")
        for block in desc_el.find_all(["br", "p", "h2", "h3", "h4", "strong"]):
            block.insert_before("\n")
        description = desc_el.get_text(separator=" ", strip=True)
        description = re.sub(r"[ \t]+", " ", description)
    else:
        description = json_ld.get("description", "")

    return title, company, location, description


def parse_generic_html(soup: BeautifulSoup) -> Tuple[str, str, str, str]:
    """Extracts job metadata and body text from generic job board HTML."""
    json_ld = _extract_json_ld_job_posting(soup)

    # Remove noise elements
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg"]):
        tag.decompose()

    title_el = soup.find("h1")
    title = (title_el.get_text(strip=True) if title_el else "") or json_ld.get("title", "")
    if not title and soup.title:
        title = soup.title.get_text(strip=True).split("|")[0].split("-")[0].strip()

    company = json_ld.get("company", "")
    if not company:
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            company = str(og_site["content"]).strip()

    location = json_ld.get("location", "")

    main_el = (
        soup.find("main")
        or soup.find("article")
        or soup.select_one("[role='main']")
        or soup.select_one(".job-description, #job-description, .description, .posting")
        or soup.body
    )

    if json_ld.get("description"):
        description = json_ld["description"]
    elif main_el:
        for li in main_el.find_all("li"):
            li.insert_before("\n- ")
        for block in main_el.find_all(["br", "p", "h2", "h3", "h4"]):
            block.insert_before("\n")
        description = main_el.get_text(separator=" ", strip=True)
        description = re.sub(r"[ \t]+", " ", description)
    else:
        description = ""

    return title, company, location, description


def _clean_bullet_line(line: str) -> str:
    """Strips leading bullet symbols and whitespace."""
    cleaned = re.sub(r"^[\s•\-\*▪▸‣◦·\d\.\)]+", "", line).strip()
    return cleaned


def extract_structured_job_details(
    raw_text: str,
    title_hint: str = "",
    company_hint: str = "",
    location_hint: str = "",
    source_url: str = "",
    source_site: str = "text",
) -> JobPostingData:
    """
    Deterministically parses raw job description text into structured sections:
    - job_title & company
    - responsibilities
    - required_qualifications
    - preferred_qualifications
    - skills & keywords
    - tone_and_culture
    Also upgrades with Gemini Structured Output if GEMINI_API_KEY is configured.
    """
    text = (raw_text or "").strip()
    if not text:
        raise JobScrapeError(
            "The job description text is empty. Please paste the full job description.",
            code="EMPTY_JOB_TEXT",
            source_url=source_url,
        )

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 1. Infer title & company if not provided by HTML tags
    job_title = title_hint.strip()
    company = company_hint.strip()
    location = location_hint.strip()

    for line in lines[:8]:
        if not job_title:
            m_title = re.match(r"^(?:job\s*title|role|position)\s*[:\-]\s*(.+)$", line, re.I)
            if m_title:
                job_title = m_title.group(1).strip()
        if not company:
            m_comp = re.match(r"^(?:company|organization|employer)\s*[:\-]\s*(.+)$", line, re.I)
            if m_comp:
                company = m_comp.group(1).strip()
        if not location:
            m_loc = re.match(r"^(?:location)\s*[:\-]\s*(.+)$", line, re.I)
            if m_loc:
                location = m_loc.group(1).strip()

    if not job_title and lines:
        # Use first short heading line if it looks like a role title
        first_line = _clean_bullet_line(lines[0])
        if len(first_line) <= 90 and not first_line.endswith("."):
            if " at " in first_line and not company:
                parts = first_line.split(" at ", 1)
                job_title = parts[0].strip()
                company = parts[1].strip()
            else:
                job_title = first_line

    if not job_title:
        job_title = "Target Role"
    if not company:
        company = "Hiring Organization"

    # 2. Classify lines into sections (Responsibilities, Required, Preferred)
    responsibilities: List[str] = []
    required_quals: List[str] = []
    preferred_quals: List[str] = []
    unclassified_bullets: List[str] = []

    current_bucket = "general"

    resp_header_re = re.compile(
        r"^(?:key\s+)?(?:responsibilities|what\s+you(?:'ll|\s+will)\s+do|the\s+role|duties|day[- ]to[- ]day|your\s+impact|in\s+this\s+role)\b[:\s]*$",
        re.I,
    )
    req_header_re = re.compile(
        r"^(?:required\s+qualifications|requirements|minimum\s+qualifications|what\s+you\s+bring|what\s+we(?:'re|\s+are)\s+looking\s+for|must\s+have|about\s+you|qualifications|skills\s+&\s+experience)\b[:\s]*$",
        re.I,
    )
    pref_header_re = re.compile(
        r"^(?:preferred\s+qualifications|nice\s+to\s+have|bonus\s+points|desired\s+qualifications|preferred\s+skills|plus(?:es)?)\b[:\s]*$",
        re.I,
    )
    culture_header_re = re.compile(
        r"^(?:about\s+us|our\s+culture|why\s+join\s+us|benefits|perks|what\s+we\s+offer)\b[:\s]*$",
        re.I,
    )

    for line in lines:
        clean_header = re.sub(r"[:\-*#]+$", "", line).strip()
        if len(clean_header) < 65:
            if resp_header_re.match(clean_header):
                current_bucket = "resp"
                continue
            if pref_header_re.match(clean_header):
                current_bucket = "pref"
                continue
            if req_header_re.match(clean_header):
                current_bucket = "req"
                continue
            if culture_header_re.match(clean_header):
                current_bucket = "culture"
                continue

        is_bullet = bool(re.match(r"^[\•\-\*▪▸‣◦·]|\d+[\.\)]", line))
        item_text = _clean_bullet_line(line)
        if len(item_text) < 12 or item_text.lower() == job_title.lower():
            continue

        # Heuristic classification if no explicit headers or inside general bucket
        lower_item = item_text.lower()
        if current_bucket == "resp":
            responsibilities.append(item_text)
        elif current_bucket == "pref":
            preferred_quals.append(item_text)
        elif current_bucket == "req":
            required_quals.append(item_text)
        elif current_bucket == "general" and (is_bullet or len(item_text) < 220):
            if any(
                kw in lower_item
                for kw in (
                    "nice to have",
                    "preferred",
                    "bonus",
                    "ideally",
                    "a plus",
                    "desirable",
                )
            ):
                preferred_quals.append(item_text)
            elif any(
                kw in lower_item
                for kw in (
                    "years of experience",
                    "years' experience",
                    "yr+",
                    "years+",
                    "bachelor",
                    "master",
                    "degree in",
                    "proficiency in",
                    "proficient in",
                    "proven experience",
                    "strong knowledge",
                    "hands-on experience",
                    "experience with",
                    "expertise in",
                    "familiarity with",
                )
            ):
                required_quals.append(item_text)
            elif any(
                lower_item.startswith(verb)
                for verb in (
                    "design",
                    "build",
                    "develop",
                    "lead",
                    "manage",
                    "architect",
                    "collaborate",
                    "implement",
                    "maintain",
                    "own",
                    "drive",
                    "partner",
                    "write",
                    "deliver",
                    "optimize",
                    "mentor",
                    "create",
                )
            ):
                responsibilities.append(item_text)
            elif is_bullet:
                unclassified_bullets.append(item_text)

    # Distribute unclassified bullets if specific buckets are empty
    if not responsibilities and not required_quals and unclassified_bullets:
        mid = max(1, len(unclassified_bullets) // 2)
        responsibilities.extend(unclassified_bullets[:mid])
        required_quals.extend(unclassified_bullets[mid:])
    elif not required_quals and unclassified_bullets:
        required_quals.extend(unclassified_bullets)
    elif not responsibilities and unclassified_bullets:
        responsibilities.extend(unclassified_bullets)

    # Fallback sentence splitting if prose paragraph job description was provided
    if not responsibilities and not required_quals:
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if 20 <= len(s.strip()) <= 260
        ]
        for sent in sentences:
            low = sent.lower()
            if any(w in low for w in ("preferred", "nice to have", "bonus", "plus")):
                preferred_quals.append(sent)
            elif any(
                w in low
                for w in ("experience", "skill", "degree", "proficient", "knowledge", "require")
            ):
                required_quals.append(sent)
            else:
                responsibilities.append(sent)

    # 3. Extract Skills & Keywords
    detected_skills: List[str] = []
    seen_lower = set()
    for skill in KNOWN_SKILLS_AND_KEYWORDS:
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(skill) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, text, re.IGNORECASE):
            if skill.lower() not in seen_lower:
                seen_lower.add(skill.lower())
                detected_skills.append(skill)

    # Also extract genuine technical acronyms (2-6 chars uppercase, e.g. AHS, DSS, GNSS, FMS, PLC, SCADA)
    # or camelCase/PascalCase technologies (e.g. MineStar, React, Docker).
    # STRICTLY ignore proper nouns (companies, mine sites), locations, rosters, common verbs, and prepositions.
    extra_keywords: List[str] = list(detected_skills)
    
    # Exclude list for non-technical words, company names, mine sites, locations, rosters, and common syntax words
    non_skill_tokens = {
        "the", "this", "that", "with", "from", "your", "you", "our", "we", "are", "will", "have",
        "for", "and", "but", "not", "who", "what", "why", "how", "about", "role", "job", "team",
        "work", "company", "experience", "skills", "required", "preferred", "responsibilities",
        "qualifications", "location", "remote", "hybrid", "senior", "junior", "lead", "staff",
        "principal", "engineer", "developer", "manager", "bachelor", "master", "as", "following",
        "operation", "operations", "ensure", "ensuring", "conduct", "conducting", "maintain",
        "maintaining", "support", "supporting", "provide", "providing", "champion", "championing",
        "collaborate", "collaborating", "manage", "managing", "working", "candidate", "successful",
        "duties", "please", "apply", "mining", "fifo", "dido", "pls", "pilbara", "western",
        "australia", "perth", "kalgoorlie", "pilgangoora", "colina", "jundee", "yandi", "kcgm",
        "bhp", "rio", "tinto", "fortescue", "fmg", "chevron", "woodside", "westrac", "caterpillar",
        "northern", "star", "resources", "position", "opportunity", "competitive", "salary",
        "package", "bonus", "superannuation", "super", "leave", "annual", "sick", "full", "time",
        "part", "permanent", "contract", "fixed", "term", "day", "night", "shift", "roster",
        "health", "safety", "environment", "culture", "equal", "opportunity", "adjustments",
        "access", "points", "site", "sites", "mine", "mines", "key", "high", "strict", "statutory",
        "wa", "nsw", "qld", "vic", "sa", "tas", "nt", "act", "usa", "uk", "au", "asap", "eeo",
        "hse", "ohs", "whs", "hr", "ceo", "cfo", "cto", "coo", "am", "pm",
    }
    
    # Add company and location words to non_skill_tokens
    for part in re.split(r"[\s,\-/]+", f"{company} {location}".lower()):
        if part.strip():
            non_skill_tokens.add(part.strip())

    # Find candidates for extra technical keywords
    tokens = re.findall(r"\b[A-Za-z0-9\+\#\.\-]{2,20}\b", text)
    for tok in tokens:
        tok_clean = tok.strip(".-")
        tok_low = tok_clean.lower()
        if tok_low in non_skill_tokens or tok_low in seen_lower or len(tok_clean) < 2:
            continue

        # Accept if:
        # A) All-uppercase technical acronym of length 2-6 (e.g. AHS, DSS, GNSS, GPS, FMS, PLC, SCADA, RTK, OT)
        # B) Mixed-case/CamelCase identifier (e.g. MineStar, PyTorch, AutoCAD)
        is_acronym = tok_clean.isupper() and 2 <= len(tok_clean) <= 6 and tok_clean.isalpha()
        is_mixed_case = any(c.isupper() for c in tok_clean[1:]) and not tok_clean.isupper()

        if is_acronym or is_mixed_case:
            seen_lower.add(tok_low)
            extra_keywords.append(tok_clean)
            # If it's a technical acronym, also add to detected_skills
            if is_acronym and tok_clean not in detected_skills:
                detected_skills.append(tok_clean)
            if len(extra_keywords) >= 20:
                break

    # 4. Extract Tone & Culture signals
    tone_signals: List[str] = []
    for label, patterns in CULTURE_SIGNALS_MAP.items():
        if any(re.search(pat, text, re.I) for pat in patterns):
            tone_signals.append(label)
    if not tone_signals:
        tone_signals.append("Professional & results-oriented")

    job_data = JobPostingData(
        job_title=job_title,
        company=company,
        location=location,
        source_url=source_url,
        source_site=source_site,
        responsibilities=responsibilities[:12],
        required_qualifications=required_quals[:12],
        preferred_qualifications=preferred_quals[:8],
        skills=detected_skills[:20],
        keywords=extra_keywords[:25],
        tone_and_culture=tone_signals,
        raw_text=text,
    )

    # Optional Gemini AI enrichment if API key is configured
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if api_key:
        try:
            job_data = _enrich_job_with_gemini(job_data, api_key)
        except Exception as exc:
            logger.warning("Gemini job enrichment skipped, using deterministic parse: %s", exc)

    return job_data


def _enrich_job_with_gemini(base_job: JobPostingData, api_key: str) -> JobPostingData:
    """Uses Gemini 3.8 Flash structured output to refine job posting extraction."""
    from google import genai

    client = genai.Client(api_key=api_key)
    model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash") or "gemini-3.8-flash"

    prompt = (
        "Extract structured job posting information from the following job description text. "
        "Preserve exact technical skills, required qualifications, preferred qualifications, "
        "responsibilities, and tone/culture signals.\n\n"
        f"Job Description:\n{base_job.raw_text[:12000]}"
    )

    interaction = client.interactions.create(
        model=model_name,
        input=prompt,
        store=False,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": JobPostingData.model_json_schema(),
        },
    )
    if interaction and interaction.output_text:
        parsed = JobPostingData.model_validate_json(interaction.output_text)
        parsed.source_url = base_job.source_url
        parsed.source_site = base_job.source_site
        parsed.raw_text = base_job.raw_text
        if not parsed.skills:
            parsed.skills = base_job.skills
        if not parsed.keywords:
            parsed.keywords = base_job.keywords
        return parsed
    return base_job


def scrape_or_parse_job(
    job_url: Optional[str] = None,
    job_text: Optional[str] = None,
) -> JobPostingData:
    """
    Main entry point for Deliverable 2:
    - If `job_text` is provided directly (or as fallback), parses it immediately.
    - If `job_url` is provided, fetches and parses LinkedIn, Seek, or generic job board HTML.
    - If the URL is blocked, requires authentication, or has insufficient job content,
      raises `JobScrapeError` with `requires_paste_fallback=True` unless `job_text` is also supplied.
    """
    clean_url = (job_url or "").strip()
    clean_text = (job_text or "").strip()

    if clean_url:
        source_site = detect_source_site(clean_url)
        try:
            html = fetch_job_html(clean_url)
            soup = BeautifulSoup(html, "html.parser")

            if source_site == "linkedin":
                title, company, location, extracted_text = parse_linkedin_html(soup)
            elif source_site == "seek":
                title, company, location, extracted_text = parse_seek_html(soup)
            else:
                title, company, location, extracted_text = parse_generic_html(soup)

            # Check for login wall text or sparse scraped content
            lower_html = html.lower()
            if len(extracted_text.strip()) < 80:
                for pat in LOGIN_WALL_PATTERNS:
                    if re.search(pat, lower_html):
                        raise JobScrapeError(
                            f"The {source_site.capitalize()} page requires authentication or blocked automated extraction. Please paste the job description text below to continue.",
                            code="JOB_LOGIN_WALL",
                            source_url=clean_url,
                        )
                raise JobScrapeError(
                    "Could not extract enough job description details from the provided link. Please paste the job description text directly.",
                    code="JOB_PARSE_INSUFFICIENT",
                    source_url=clean_url,
                )

            return extract_structured_job_details(
                raw_text=extracted_text,
                title_hint=title,
                company_hint=company,
                location_hint=location,
                source_url=clean_url,
                source_site=source_site,
            )
        except JobScrapeError:
            # If the user ALSO provided fallback job_text in the same request, gracefully use it!
            if clean_text:
                return extract_structured_job_details(
                    raw_text=clean_text,
                    source_url=clean_url,
                    source_site=source_site,
                )
            raise

    if clean_text:
        return extract_structured_job_details(
            raw_text=clean_text,
            source_url="",
            source_site="text",
        )

    raise JobScrapeError(
        "Please provide either a job posting URL or paste the job description text.",
        code="MISSING_JOB_INPUT",
        requires_paste_fallback=True,
    )
