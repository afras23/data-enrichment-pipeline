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

## Decision (strategic)

The **target** architecture is **Option A (search-assisted discovery)** with **Option B (heuristic probes)** as a **fallback** when search is unavailable or returns no confident candidate. **Option C (LLM-only URL inference)** remains **out of scope** as a primary path.

## Implementation (current codebase)

The shipped service implements **Option B only** (`WebsiteDiscoveryService` in `app/services/website_discovery.py`):

- Derive a **slug** from the company name (`normalize_company_key`).
- Probe **`https://www.{slug}.com/`**, **`https://{slug}.com/`**, then **`.io`** variants (order influenced by `DISCOVERY_TRY_WWW`).
- Accept the first response that **looks like HTML** with a successful status; attach **confidence** (e.g. higher when the resolved URL uses `www`).
- Persist **`candidates_tried`** and notes in `discovery_metadata` on the enrichment record.

A **search API** integration remains a **future improvement**; until then, discovery is fully **mockable** over HTTP for tests and evaluation.

## Consequences

- **Positive:** No third-party search dependency in the default build; simple CI; predictable behaviour for portfolio demos.
- **Negative:** Lower recall on brands whose domains do not match the slug heuristic; operators rely on **website_confidence** and **partial** states when no candidate works.
- **Follow-up:** Add Option A behind configuration; optional Option D-style re-ranking among search candidates.
