# Problem Definition: Data Extraction & Enrichment Pipeline

## Business context

Mid-market and enterprise B2B sales organisations routinely acquire prospect lists—event registrations, partner referrals, purchased lead files—with **company names only** and little or no firmographic structure. Revenue teams, SDRs, and account researchers must turn those names into usable account records (industry, approximate size, technology footprint, and contact hints) before outreach or CRM import.

The pain is acute in **high-volume outbound** and **territory planning**, where thousands of rows arrive at once and manual research does not scale.

## Current manual process

Typical steps per company name:

1. **Search** for the official website (search engine, LinkedIn, news).
2. **Open** the site and skim **About**, **Careers**, **Contact**, and sometimes **footer** text.
3. **Infer** industry and company size from wording, job titles, and office locations.
4. **Guess** tech stack from job postings, marketing pages, or built-with hints.
5. **Note** generic or role-based contacts (for example `info@`, `sales@`) where visible.
6. **Copy** findings into a spreadsheet or CRM.

**Time:** roughly **3–10 minutes per company**, depending on ambiguity and researcher familiarity.

**Frequency:** During list drops or campaign prep, often **hundreds to thousands of rows per batch** (the original project brief cites on the order of **~5,000 names** with no structured data).

## Pain points

- **Throughput:** Manual research cannot clear large lists without a large team or long delays.
- **Consistency:** Different researchers tag industries and sizes differently; tech stack notes are ad hoc.
- **Error risk:** Wrong website, outdated size band, or rushed inference.
- **Key-person risk:** Tribal knowledge lives in senior reps; absence or turnover stalls enrichment.
- **Downstream friction:** CRM and sequencing tools need **structured fields**, not paragraphs of notes.

## Automation opportunity

| Step | Automate | Human judgement |
|------|----------|-----------------|
| Resolve company → canonical website | Yes (with confidence score) | Override when brand collision or rebranding |
| Fetch and extract text from public pages | Yes | Policy on which pages are in scope |
| Classify industry, size band, tech themes | Yes (LLM + validation) | Review low-confidence or regulated sectors |
| Extract or surface contact channels | Yes (from scraped text only) | Compliance review for outreach use |
| Aggregate **data quality score** | Yes | Define thresholds for “ready to use” |

**Expected impact:** Reduce **minutes per row to seconds** on the automated path; keep a **small review slice** for ambiguous cases without blocking the whole batch.

## Inputs

- **Primary input:** A list of **company names** (optional locale, country, or URL hints can be layered later—only in scope when explicitly added to the product).
- **Format:** Batch submission via API (JSON body with a `companies` array); internal normalisation uses a **normalised name key** for indexing and deduplication hints.
- **Volume:** Design target **up to ~5,000 companies per run** with configurable concurrency and **per-run cost limits**.
- **Worst-case inputs:** Ambiguous names (“Acme”, “Vertex”), non-English pages, parked domains, JavaScript-heavy sites with little static HTML, rate limits from external services.

## Outputs

- **Enriched records** per company, including at minimum:

  - Industry (structured label).
  - Size (employee band such as `51-200`).
  - Tech stack (list of tags).
  - Contacts or signals (emails, phone patterns, social links derived from scraped content—subject to policy).

- **Data quality score** per record (`final_score` and subscores), suitable for filtering before CRM sync.

- **Auditability:** Prompt version, model id, token usage, discovery metadata, scrape bundle summary, correlation id where provided.

Downstream systems are not fixed in scope; the deliverable is an **API plus persisted structured data** so CRM or warehouse ingestion can be added without changing the core enrichment contract.

## Failure modes

| Failure | Mitigation |
|---------|------------|
| Model output wrong or inconsistent | Pydantic validation, composite quality score; low scores visible in `quality_report` |
| Wrong website chosen | Discovery confidence stored; explicit failure when no candidate resolves |
| Site unreachable or blocked | Terminal partial/failed states with error codes—not silent empty success |
| OpenAI outage or 429 | Client error handling; run-level aggregates reflect partial completion |
| Scraping legal or ToS concerns | Fetch public pages only; configurable user-agent and limits; document policy in runbook |

**Human fallback:** Re-run specific companies in a new batch; use quality thresholds to triage review (a full review UI is out of scope unless added later).

## Success criteria

- **Functional:** For representative sample companies, the pipeline produces **schema-valid** enriched records and **non-trivial** quality scores.
- **Reliability:** A full run completes with **per-row terminal states** (completed, partial, failed) and **auditable** batch tracking.
- **Observability:** Health, readiness, and metrics endpoints; structured logs with **correlation IDs**.
- **Cost and latency:** Per-company AI cost and duration persisted; **per-run cost cap** enforced in configuration.
- **Quality:** Automated tests with **mocked** HTTP and LLM in CI; optional **offline evaluation** via `make evaluate` (see `eval/README.md`).

These criteria align with a production-oriented pipeline—not demo-only happy paths.

## Related documentation

- **`docs/architecture.md`** — Components and sequence diagrams.
- **`docs/runbook.md`** — Operations, tuning, evaluation.
- **`docs/decisions/`** — ADRs for discovery, AI, quality, storage, and retries.
