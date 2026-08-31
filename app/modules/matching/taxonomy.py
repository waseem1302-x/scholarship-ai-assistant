"""Academic discipline and field-of-study taxonomy for intelligent scholarship matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

ACADEMIC_TAXONOMY: dict[str, dict[str, tuple[str, ...]]] = {
    "Computer Science & Information Technology": {
        "cluster_key": "computer_science_it",
        "keywords": (
            "computer science",
            "software engineering",
            "information technology",
            "information tech",
            "informatics",
            "data science",
            "data analytics",
            "machine learning",
            "artificial intelligence",
            "ai",
            "cybersecurity",
            "cyber security",
            "information systems",
            "cloud computing",
            "computer engineering",
            "natural language processing",
            "nlp",
            "robotics",
            "computer networks",
            "human computer interaction",
            "hci",
            "computational science",
            "software development",
            "web development",
            "computational biology",
            "bioinformatics",
        ),
    },
    "Engineering & Technology": {
        "cluster_key": "engineering_technology",
        "keywords": (
            "engineering",
            "electrical engineering",
            "electronic engineering",
            "electronics engineering",
            "mechanical engineering",
            "civil engineering",
            "chemical engineering",
            "aerospace engineering",
            "aeronautical engineering",
            "materials engineering",
            "biomedical engineering",
            "industrial engineering",
            "systems engineering",
            "environmental engineering",
            "mechatronics",
            "telecommunications engineering",
            "structural engineering",
            "petroleum engineering",
            "automotive engineering",
            "nuclear engineering",
        ),
    },
    "Natural Sciences & Mathematics": {
        "cluster_key": "natural_sciences_math",
        "keywords": (
            "mathematics",
            "applied mathematics",
            "pure mathematics",
            "statistics",
            "physics",
            "applied physics",
            "chemistry",
            "biochemistry",
            "biology",
            "biological sciences",
            "molecular biology",
            "microbiology",
            "genetics",
            "ecology",
            "earth sciences",
            "geology",
            "geophysics",
            "astronomy",
            "astrophysics",
            "neuroscience",
            "materials science",
            "natural sciences",
            "stem",
        ),
    },
    "Health & Medical Sciences": {
        "cluster_key": "health_medical_sciences",
        "keywords": (
            "medicine",
            "medical sciences",
            "nursing",
            "public health",
            "global health",
            "pharmacy",
            "pharmacology",
            "dentistry",
            "dental surgery",
            "clinical research",
            "epidemiology",
            "health informatics",
            "veterinary medicine",
            "physiotherapy",
            "nutrition",
            "immunology",
            "biomedical sciences",
            "healthcare management",
            "health policy",
        ),
    },
    "Business, Economics & Finance": {
        "cluster_key": "business_economics_finance",
        "keywords": (
            "business",
            "business administration",
            "mba",
            "management",
            "finance",
            "accounting",
            "economics",
            "applied economics",
            "econometrics",
            "marketing",
            "international business",
            "entrepreneurship",
            "supply chain management",
            "logistics",
            "human resource management",
            "hrm",
            "fintech",
            "banking",
            "commerce",
        ),
    },
    "Social Sciences & Policy": {
        "cluster_key": "social_sciences_policy",
        "keywords": (
            "social sciences",
            "political science",
            "politics",
            "international relations",
            "public policy",
            "public administration",
            "sociology",
            "psychology",
            "anthropology",
            "development studies",
            "international development",
            "education",
            "educational leadership",
            "criminology",
            "social work",
            "human rights",
            "urban planning",
            "geography",
            "communication studies",
            "journalism",
            "media studies",
        ),
    },
    "Humanities, Arts & Law": {
        "cluster_key": "humanities_arts_law",
        "keywords": (
            "law",
            "legal studies",
            "llm",
            "international law",
            "humanities",
            "history",
            "philosophy",
            "literature",
            "linguistics",
            "languages",
            "cultural studies",
            "theology",
            "religious studies",
            "fine arts",
            "design",
            "architecture",
            "music",
            "performing arts",
            "visual arts",
            "film studies",
        ),
    },
    "Agriculture & Environmental Sciences": {
        "cluster_key": "agriculture_environmental",
        "keywords": (
            "agriculture",
            "agricultural science",
            "agronomy",
            "forestry",
            "horticulture",
            "environmental science",
            "environmental studies",
            "sustainability",
            "sustainable development",
            "climate change",
            "soil science",
            "fisheries",
            "marine science",
            "food science",
            "food technology",
            "renewable energy",
        ),
    },
}


@dataclass(frozen=True, slots=True)
class FieldMatchResult:
    matched: bool
    score: float  # 1.0 = exact, 0.85 = cluster sibling, 0.0 = no match
    cluster_name: str | None = None
    explanation: str = ""


def _clean_token(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower().strip())


def get_field_cluster(field_name: str | None) -> tuple[str, str] | None:
    """Find the canonical category and cluster key for a given academic field."""
    cleaned = _clean_token(field_name)
    if not cleaned:
        return None
    for category_name, data in ACADEMIC_TAXONOMY.items():
        keywords = data["keywords"]
        for kw in keywords:
            if kw == cleaned or kw in cleaned or cleaned in kw:
                return category_name, data["cluster_key"]
    return None


def match_fields_of_study(
    student_fields: list[str] | str,
    scholarship_fields: list[str] | str,
) -> FieldMatchResult:
    """Match student fields against scholarship target fields using exact and taxonomy rules.

    Args:
        student_fields: Student's intended field, discipline, or detail.
        scholarship_fields: List of eligible fields or single required field.

    Returns:
        FieldMatchResult with matched boolean, score weight multiplier, and explanation.
    """
    if isinstance(student_fields, str):
        student_list = [student_fields]
    else:
        student_list = [f for f in student_fields if f]

    if isinstance(scholarship_fields, str):
        req_list = [scholarship_fields]
    else:
        req_list = [f for f in scholarship_fields if f]

    if not student_list or not req_list:
        return FieldMatchResult(matched=False, score=0.0, explanation="Missing field inputs")

    cleaned_student = [_clean_token(s) for s in student_list if _clean_token(s)]
    cleaned_req = [_clean_token(r) for r in req_list if _clean_token(r)]

    # 1. Check for universal match / any
    if any(req in {"any", "all", "all fields", "all disciplines", "open"} for req in cleaned_req):
        return FieldMatchResult(
            matched=True,
            score=1.0,
            explanation="Open to all fields of study",
        )

    # 2. Check for exact literal or substring match
    for s in cleaned_student:
        for r in cleaned_req:
            if s == r:
                return FieldMatchResult(
                    matched=True,
                    score=1.0,
                    explanation=f"Direct match on field: '{r}'",
                )
            if len(s) >= 4 and len(r) >= 4 and (s in r or r in s):
                return FieldMatchResult(
                    matched=True,
                    score=1.0,
                    explanation=f"Close keyword match between '{s}' and '{r}'",
                )

    # 3. Check for taxonomy cluster match (e.g. Machine Learning -> Computer Science)
    student_clusters = set()
    for s in cleaned_student:
        cluster = get_field_cluster(s)
        if cluster:
            student_clusters.add(cluster)

    for r in cleaned_req:
        req_cluster = get_field_cluster(r)
        if req_cluster and req_cluster in student_clusters:
            category_name = req_cluster[0]
            return FieldMatchResult(
                matched=True,
                score=0.85,
                cluster_name=category_name,
                explanation=f"Academic cluster match in '{category_name}'",
            )

    return FieldMatchResult(
        matched=False,
        score=0.0,
        explanation="Field of study does not match target scholarship requirements",
    )
