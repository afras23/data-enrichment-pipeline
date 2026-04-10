# ADR 001: Website Discovery Strategy

## Status

Accepted

## Context

The pipeline must map a **plain company name** to an **official public website** before scraping and LLM enrichment. Names are often ambiguous (collisions, regional subsidiaries, rebrands). Discovery must be **automatable**, **auditable**, and **safe** (avoid phishing or unrelated domains).

Constraints:

- Portfolio stack is **Python**; discovery must fit async services and tests with **mocked** HTTP.
- **10–12 hour** project scope: avoid building a full search appliance; prefer a small number of well-understood strategies.
- Outcomes must include **confidence** and **candidate traceability** for downstream quality scoring.

## Options Considered

### Option A: Search API + ranking heuristics

Use a web search provider (e.g. Bing/Google programmable search) with queries like `"{name}" official site`, take top organic results, score by title/snippet match, TLD trust, HTTPS, and domain-token overlap with the company name.

- **Pro:** High recall on real-world names; handles non-obvious domains.
- **Con:** Extra API key, cost, and usage terms; another external dependency to mock and monitor.

### Option B: Heuristic URL guessing only

Try deterministic URLs (`https://{slug}.com`, common variants) with HTTP HEAD/GET validation.

- **Pro:** No search dependency; simple; fast tests.
- **Con:** Poor recall for brands that do not match DNS slug; many false negatives.

### Option C: LLM-only URL inference

Ask the model for the company homepage URL from the name alone.

- **Pro:** Minimal plumbing.
- **Con:** High hallucination risk for URLs; violates “never trust AI output” without verification; hard to audit.

### Option D: Search API + LLM re-ranking (hybrid)

Search API produces candidates; a **small** LLM step re-ranks or explains best match **only among candidates** returned by search, with strict JSON schema and fallback to heuristics if uncertain.

- **Pro:** Better precision than raw search alone; LLM constrained to provided URLs.
- **Con:** Additional LLM cost and latency; more moving parts.

## Decision

Adopt **Option A (Search API + ranking heuristics)** as the **primary** strategy for v1, with **Option B** as a **fallback** when search is disabled or returns no confident result (config flag). **Do not** use Option C as a primary path.

Ranking features (non-exhaustive): normalised name similarity, presence of company name in title/description, domain age signals if available without heavy dependencies, HTTPS, and penalisation of obvious aggregators (LinkedIn, Crunchbase) unless no alternative exists—exact rules live in code and settings.

If a search API is **not** configured in a given deployment, the system falls back to **Option B** explicitly and records `discovery_source=heuristic` for quality scoring transparency.

## Consequences

- **Positive:** Better real-world recall than pure guessing; auditable candidate lists; clear separation between “no website found” and “website found but low confidence.”
- **Negative:** Requires a search API key and compliance with provider ToS; tests must mock search responses; CI must not call live search.
- **Follow-up (out of scope unless scheduled):** optional **Option D** as a precision pass when search returns multiple close candidates.
