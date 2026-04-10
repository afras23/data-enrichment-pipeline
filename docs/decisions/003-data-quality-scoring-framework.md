# ADR 003: Data Quality Scoring Framework

## Status

Accepted

## Context

Downstream users need to **filter** and **trust** enriched records at scale. A single scalar **data quality score** (plus optional subscores) supports routing, SLA-style thresholds, and demo credibility (“quality scoring” is an explicit project outcome).

Requirements:

- **Deterministic** and explainable: same inputs → same score.
- **Composite:** blend evidence from **discovery**, **scrape**, and **validated LLM output**—not LLM self-reported “confidence” alone.
- **Tunable** via configuration (weights), not hardcoded magic numbers in business logic scattered across files.

## Options Considered

### Option A: LLM self-rated confidence only

Ask the model to output a 0–1 confidence per field or overall.

- **Pro:** Fast to implement.
- **Con:** Unreliable; conflicts with “never trust AI output”; hard to defend in review.

### Option B: Rule-only scoring (no ML)

Weighted checklist: field non-null, URL HTTPS, minimum text length, etc.

- **Pro:** Fully deterministic and cheap.
- **Con:** Ignores semantic plausibility; may score incomplete but “lucky” rows too high.

### Option C: Hybrid composite score (rules + structure)

Deterministic function of:

1. **Discovery confidence** (from ADR 001 signals).
2. **Scrape coverage** (pages fetched, aggregate text length after cap, successful parse).
3. **Field completeness** on validated Pydantic model (required vs optional fields).
4. **Consistency checks** (e.g. industry enum valid; tech tags ⊆ allowlist; contact formats valid).
5. **Optional:** small penalty if **many** fields are simultaneously at boundary values (heuristic for “vague” extractions).

- **Pro:** Aligns with portfolio playbook composite pattern; explainable subscores; no extra API calls.
- **Con:** Requires careful weighting and tests to avoid gaming by long garbage text—mitigated by caps and normalisation.

### Option D: Train a small ML model on labelled good/bad rows

- **Pro:** Could correlate with human labels over time.
- **Con:** Out of scope; needs labelled data.

## Decision

Implement **Option C (hybrid composite score)** with **explicit subscores** stored alongside the final score.

**Implemented subscores** (`QualitySubscores` in `app/schemas/domain.py`, computed in `QualityScoringService`):

| Subscore | Meaning |
|----------|---------|
| `completeness` | Share of populated AI fields (six checks) |
| `evidence_strength` | Derived from visible text length, page count, fetch errors |
| `consistency` | Overlap between scraped text and industry/tech tokens |
| `website_confidence` | Discovery confidence, clamped to `[0, 1]` |

Final **`final_score`** is a **weighted sum** in **[0, 1]** with fixed code weights: **0.30** completeness + **0.30** evidence + **0.25** consistency + **0.15** website confidence (see `app/services/quality_scoring.py`). Tuning today requires a code change; moving weights to **`Settings`** is a possible follow-up.

**Thresholds:** configurable `quality_pass_threshold` for tagging rows as **“high confidence”** vs **“needs review”** in API responses—without requiring a full review UI in scope.

## Consequences

- **Positive:** Defensible scoring; works offline in tests; supports README metrics (“avg quality score”).
- **Negative:** Weights need tuning using `eval/` runs; document that scores are **relative** to configured weights.
- **API:** Responses expose `quality_score` + breakdown for transparency.
