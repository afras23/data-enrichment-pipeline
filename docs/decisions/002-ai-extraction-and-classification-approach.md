# ADR 002: AI Extraction and Classification Approach

## Status

Accepted

## Context

After public page text is collected, the system must produce **structured** fields: **industry**, **company size**, **tech stack**, and **contacts**, plus internal audit metadata. The project mandates **OpenAI API** usage and strict validation.

Challenges:

- LLMs may **hallucinate** facts not present in text.
- **Classification** labels must be comparable across rows (controlled vocabulary vs free text).
- **Contacts** are sensitive: only surface what appears in scraped public content.

## Options Considered

### Option A: Single-shot JSON extraction with Pydantic validation

One OpenAI call with a **system** instruction and a **user** message containing labelled text snippets; response must match a JSON schema; validate with Pydantic; nulls for unknown fields.

- **Pro:** Simple pipeline; one cost line per company; easy to version.
- **Con:** Long pages need aggressive truncation; may mix extraction quality across field groups.

### Option B: Multi-step: classify industry/size first, then extract tech and contacts

Two or three smaller calls with narrower prompts.

- **Pro:** Smaller contexts per call; potentially higher accuracy per task.
- **Con:** Higher latency and cost; more failure points; orchestration complexity for a 10–12h scope.

### Option C: Fine-tuned or hosted classifier for industry only

Traditional ML or fine-tuned model for industry; LLM for the rest.

- **Pro:** Possibly cheaper at scale.
- **Con:** Out of scope for this portfolio build; needs training data and ops.

### Option D: OpenAI structured outputs / JSON schema mode (if available for chosen model)

Use provider-native structured output guarantees where supported.

- **Pro:** Fewer parse failures; less brittle than manual JSON instructions.
- **Con:** Model-dependent; must still validate server-side.

## Decision

Use **Option A** as default: **one structured extraction call per company** after scraping, with **Option D** employed when the selected OpenAI model supports **structured outputs or JSON schema** in the client; otherwise, strict prompting with `response_format` where applicable and **repair-or-fail** logic (single retry with a “fix JSON” prompt) before marking the row failed.

**Classification policy:**

- **Industry:** map to a **fixed enum or taxonomy table** in code (e.g. GICS-like buckets simplified for demo); LLM returns **closest label** or `null` if unsupported.
- **Size:** return **employee band enum** (e.g. `1-10`, `11-50`, …) derived only from explicit textual evidence or `null`.
- **Tech stack:** list of **normalised tags** from an allowlist; LLM may propose tags **only** if supported by quoted hints in input snippets (enforced in prompt; validated post-hoc).
- **Contacts:** extract emails, social links, or contact page URLs **verbatim** from text; validate formats; no invented addresses.

**Prompt rules:** System prompt defines role, safety, and “do not invent”; user prompt includes **only** concatenated snippets with source tags; never intermix instructions from page content (playbook alignment).

## Implementation note (current codebase)

- **`AIEnrichmentResult`** (`app/schemas/domain.py`) uses **validated** fields: `company_size_band` is restricted to a fixed set of labels; `industry` is a **string** (not a strict taxonomy enum in code—tightening to an enum remains a future improvement).
- **Prompt version** `company_enrichment_v1` and model from **`settings.openai_model`** are persisted on each record.
- **Repair retry** for malformed JSON may be extended in `OpenAIEnrichmentClient`; rows that fail validation surface as enrichment errors.

## Consequences

- **Positive:** One place to version (`company_enrichment_v1`); easier evaluation; clear cost per company.
- **Negative:** Truncation may drop rare facts; mitigated by scraping prioritisation and snippet selection (implementation detail).
- **Testing:** All LLM calls **mocked** in CI; golden JSON fixtures for regression.
