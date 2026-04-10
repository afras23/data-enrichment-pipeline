"""
Versioned prompt templates for company enrichment.

Prompts are data — change version when altering text to preserve auditability.
"""

from __future__ import annotations

PROMPT_VERSION = "company_enrichment_v1"

SYSTEM_PROMPT = """You are a precise B2B research assistant. You receive public website text snippets \
from a company's site. Extract structured firmographic data. Return ONLY valid JSON matching the \
schema described in the user message. Use null when information is not clearly supported by the text. \
Do not invent URLs, emails, or product claims not evidenced in the input. If you cite reasoning, \
keep it brief in confidence_notes and evidence_summary."""


def build_user_prompt(
    company_name: str,
    scraped_text: str,
    deterministic_json_hint: str,
) -> str:
    """
    Build the user message containing company context and page text.

    Args:
        company_name: Target company name from the batch input.
        scraped_text: Concatenated visible text from crawled pages (bounded upstream).
        deterministic_json_hint: JSON string of deterministic scrape signals for cross-checking.
    """

    return (
        "Task: extract structured enrichment fields for the company below.\n\n"
        f"Company name: {company_name}\n\n"
        "Required JSON keys (all may be null or empty arrays where unknown):\n"
        '- "industry": string or null (short label, e.g. "FinTech SaaS")\n'
        '- "company_description": string or null (1-3 sentences)\n'
        '- "company_size_band": one of '
        '"1-10","11-50","51-200","201-500","501-1000","1000+", or null\n'
        '- "tech_stack": array of short strings (e.g. "Salesforce","React")\n'
        '- "contacts_or_signals": array of strings — emails, "contact page", social hints found in text\n'
        '- "confidence_notes": string — what was weak or ambiguous\n'
        '- "evidence_summary": string — which sections supported key claims\n\n'
        "Deterministic scrape signals (for consistency; do not copy blindly if contradicted by stronger text):\n"
        f"{deterministic_json_hint}\n\n"
        "Scraped page text (may be truncated):\n"
        "-----\n"
        f"{scraped_text}\n"
        "-----\n"
        "Return a single JSON object with exactly these keys."
    )
