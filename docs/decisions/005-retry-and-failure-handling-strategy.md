# ADR 005: Retry and Failure Handling Strategy

## Status

Accepted

## Context

The pipeline depends on **unreliable networks** (target sites), **rate limits** (HTTP and OpenAI), and **occasionally invalid LLM output**. Failures must be **classified**, **logged**, and **retried** only when appropriate to avoid duplicate cost and thundering herds.

This ADR defines cross-cutting rules consistent with the **AI Engineering Playbook** and **10/10 addendum** (retries, backoff, circuit breaker).

## Options Considered

### Option A: Retry everything blindly

- **Pro:** Simple.
- **Con:** Amplifies failures; wastes tokens; violates idempotency discipline.

### Option B: No retries

- **Pro:** Predictable cost.
- **Con:** Poor success rate on transient errors; unacceptable for a “production-grade” portfolio story.

### Option C: Tiered policies per dependency

Define **retryable vs non-retryable** exceptions per layer:

- **HTTP to customer sites:** retry connection/timeouts and **some** 5xx; do **not** retry most 4xx except `429` with backoff.
- **OpenAI:** retry timeouts, 429, and selective 5xx; **do not** retry schema validation failures without a bounded repair attempt.
- **Circuit breaker:** open after **N** consecutive failures **per host** or **global LLM** failures within a window; short-circuit with clear metrics.

### Option D: Distributed saga with compensating transactions

- **Pro:** Theoretically elegant for large systems.
- **Con:** Overkill for v1 single-service batch processor.

## Decision

Adopt **Option C (tiered policies + circuit breaker)** with these defaults (exact numbers in `Settings`):

**HTTP fetching**

- Retries: **up to 3** attempts for: connection errors, read timeouts, HTTP **502/503/504**.
- Backoff: **exponential with jitter** between attempts; per-host spacing to avoid abuse.
- No retry: **401/403/404** (terminal scrape failure unless business rules say otherwise).
- **429 from target site:** respect `Retry-After` if present; else exponential backoff with cap.

**OpenAI**

- Retries: **up to 3** for timeout, **429**, and **5xx** from API.
- **No retry** for **4xx** auth errors after validating key once.
- **JSON / schema failure:** at most **one** repair retry with a minimal “fix JSON” prompt; then mark job **failed** with `VALIDATION_ERROR`.

**Circuit breaker**

- **Per-host HTTP:** after **5** consecutive failures to the same netloc, **pause** further requests to that host for **60s** (configurable).
- **OpenAI:** after **5** consecutive failures (any job), open breaker; reject new LLM calls briefly **or** fail fast with `RetryableError` and run-level `degraded`—implementation chooses one consistently and documents in runbook.

**Run-level behaviour**

- A **single company failure** does not fail the entire batch unless configured; counters increment `failed` jobs.
- **Cost limit:** when `max_daily_cost_usd` would be exceeded, stop scheduling new LLM calls; run status `cost_limited`; jobs not yet processed remain **pending** or **cancelled** per explicit policy (pick one in implementation and document).

## Consequences

- **Positive:** Predictable behaviour under stress; good observability story; aligns with playbook.
- **Negative:** More code paths to test; requires careful unit tests for classification of exceptions.
- **Metrics:** expose retry counts, breaker state, and failure reason codes for demo credibility.
