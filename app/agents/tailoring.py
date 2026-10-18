import sys
import os
import re

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from pydantic import BaseModel, Field
from app.agents.llm_config import llm, get_text
from app.vectorstore.setup import embed_text
import numpy as np


class RewrittenBullet(BaseModel):
    original_text: str = Field(description="The original, unmodified bullet text")
    rewritten_text: str = Field(description="The rewritten bullet, reframed to better match the job requirement")
    reasoning: str = Field(description="Brief explanation of what was changed and why")


def rewrite_bullet(original_bullet: str, requirement: str, suggestion_hint: str) -> RewrittenBullet:
    """
    Rewrite a single resume bullet to better match a job requirement's
    phrasing, using ONLY facts already present in the original bullet.
    """
    structured_llm = llm.with_structured_output(RewrittenBullet)

    prompt = f"""You are rewriting a single resume bullet point to better match a job requirement's language.

Original bullet: "{original_bullet}"
Job requirement it should better match: "{requirement}"
Hint from prior analysis: "{suggestion_hint}"

STRICT RULES:
- You may ONLY rephrase, reorder, or emphasize facts, tools, and numbers that are ALREADY present in the original bullet.
- You must NOT add any new tool, technology, skill, metric, or outcome that isn't already stated in the original.
- You must NOT change any numbers (percentages, counts) that appear in the original.
- If the original bullet genuinely cannot be improved to match the requirement without inventing something, return it unchanged and explain why in the reasoning field.

Rewrite the bullet now.
"""

    return structured_llm.invoke(prompt)


# A small list of common tech/tool/methodology keywords to check for
# fabrication. Not exhaustive by design - it's one safety net among several,
# not the only line of defense (see fact_check_rewrite below for the
# LLM-based check that catches terms this list can't anticipate).
KNOWN_TECH_KEYWORDS = [
    "aws", "azure", "gcp", "docker", "kubernetes", "react", "vue", "angular",
    "python", "java", "javascript", "typescript", "sql", "nosql", "mongodb",
    "postgresql", "mysql", "flask", "django", "fastapi", "node", "express",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "spark",
    "airflow", "kafka", "redis", "graphql", "rest", "grpc", "terraform",
    "jenkins", "ci/cd", "git", "github", "gitlab", "linux", "bash",
    "etl", "elt", "microservices", "agile", "scrum", "devops", "mlops",
    "ci", "cd", "tdd", "oop", "mvc", "serverless", "containerization",
    "orchestration", "streaming", "batch processing",
]


def extract_tech_keywords(text: str) -> set[str]:
    """Find which known tech keywords appear in a piece of text."""
    text_lower = text.lower()
    found = set()
    for keyword in KNOWN_TECH_KEYWORDS:
        if re.search(r"\b" + re.escape(keyword) + r"\b", text_lower):
            found.add(keyword)
    return found


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a = np.array(vec_a)
    b = np.array(vec_b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)



class ValidationResult(BaseModel):
    is_safe: bool
    similarity_score: float
    new_keywords_introduced: list[str]
    flagged_reason: str = ""


def validate_rewrite(original: str, rewritten: str, similarity_threshold: float = 0.75) -> ValidationResult:
    """
    Independently checks a rewritten bullet for fabrication risk,
    regardless of what the rewriting LLM claimed about itself.
    """
    original_keywords = extract_tech_keywords(original)
    rewritten_keywords = extract_tech_keywords(rewritten)
    new_keywords = rewritten_keywords - original_keywords

    original_vec = embed_text(original)
    rewritten_vec = embed_text(rewritten)
    similarity = cosine_similarity(original_vec, rewritten_vec)

    is_safe = True
    reasons = []

    if new_keywords:
        is_safe = False
        reasons.append(f"introduces new tech keywords not in original: {new_keywords}")

    if similarity < similarity_threshold:
        is_safe = False
        reasons.append(f"semantic drift too high (similarity={similarity:.3f}, threshold={similarity_threshold})")

    return ValidationResult(
        is_safe=is_safe,
        similarity_score=round(similarity, 4),
        new_keywords_introduced=list(new_keywords),
        flagged_reason="; ".join(reasons),
    )


class FactCheckResult(BaseModel):
    has_unsupported_claim: bool = Field(description="True if the rewritten text claims anything not present in the original")
    unsupported_claims: list[str] = Field(description="List of specific claims/terms in the rewrite that aren't backed by the original text")
    explanation: str = Field(description="Brief explanation of the judgment")


def fact_check_rewrite(original: str, rewritten: str) -> FactCheckResult:
    """
    An independent LLM call whose ONLY job is to compare original vs rewritten
    text and catch any claim, term, or specificity added that wasn't in the
    original - this catches things no fixed keyword list can (e.g. specific
    methodologies, implied scale, implied outcomes).
    """
    structured_llm = llm.with_structured_output(FactCheckResult)

    prompt = f"""Compare these two pieces of text. The REWRITTEN text should express
ONLY facts already present in the ORIGINAL text, just possibly reworded.

ORIGINAL: "{original}"
REWRITTEN: "{rewritten}"

Carefully check: does the REWRITTEN text state, imply, or name ANY specific
technology, methodology, tool, scale, outcome, or fact that is NOT explicitly
present in the ORIGINAL? Be strict - a more specific or technical term than
what appears in the original counts as an unsupported claim, even if it seems
like a reasonable inference (e.g. "data pipelines" becoming "ETL pipelines" is
an unsupported claim, since ETL is a specific technical claim not stated in
the original).

Respond with your judgment.
"""

    return structured_llm.invoke(prompt)


def full_validation(original: str, rewritten: str) -> dict:
    """Runs BOTH the keyword/similarity check AND the LLM fact-checker,
    combining them into one final safety verdict."""
    keyword_check = validate_rewrite(original, rewritten)
    fact_check = fact_check_rewrite(original, rewritten)

    is_safe = keyword_check.is_safe and not fact_check.has_unsupported_claim

    return {
        "is_safe": is_safe,
        "keyword_check": keyword_check.model_dump(),
        "fact_check": fact_check.model_dump(),
    }


if __name__ == "__main__":
    print("=== BULLET REWRITING + VALIDATION TEST ===\n")

    test_cases = [
        {
            "original": "Processed and analyzed 3K+ records for data preprocessing, exploratory data analysis (EDA), reporting, and model development.",
            "requirement": "ETL pipeline development",
            "hint": "This relates to data preprocessing work but doesn't explicitly say 'pipeline' or 'ETL'.",
        },
        {
            "original": "Developed and deployed a MERN-stack business application for workflow automation, project tracking, and team collaboration.",
            "requirement": "AWS cloud experience",
            "hint": "No evidence of AWS anywhere - this should likely be returned unchanged.",
        },
        {
            "original": "Built automated data pipelines and time-series forecasting models to generate insights from large environmental datasets.",
            "requirement": "Apache Kafka streaming experience",
            "hint": "Try to connect this to Kafka if at all possible.",
        },
    ]

    for case in test_cases:
        result = rewrite_bullet(case["original"], case["requirement"], case["hint"])
        validation = validate_rewrite(result.original_text, result.rewritten_text)

        print(f"Requirement: {case['requirement']}")
        print(f"Original:  {result.original_text}")
        print(f"Rewritten: {result.rewritten_text}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Validation: {'✅ SAFE' if validation.is_safe else '🚫 FLAGGED'}")
        print(f"  Similarity: {validation.similarity_score}")
        if not validation.is_safe:
            print(f"  Reason: {validation.flagged_reason}")
        print()

    print("\n=== FULL VALIDATION TEST (the ETL case that slipped through before) ===\n")
    original = "Built automated data pipelines and time-series forecasting models to generate insights from large environmental datasets."
    rewritten = "Built automated ETL pipelines and time-series forecasting models to generate insights from large environmental datasets."

    result = full_validation(original, rewritten)
    print(f"Original:  {original}")
    print(f"Rewritten: {rewritten}")
    print(f"\nFinal verdict: {'✅ SAFE' if result['is_safe'] else '🚫 FLAGGED'}")
    print(f"Keyword check safe: {result['keyword_check']['is_safe']}")
    print(f"Fact-check unsupported claim: {result['fact_check']['has_unsupported_claim']}")
    if result['fact_check']['unsupported_claims']:
        print(f"Unsupported claims found: {result['fact_check']['unsupported_claims']}")
    print(f"Fact-check explanation: {result['fact_check']['explanation']}")