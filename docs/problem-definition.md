# Problem Definition: Data Extraction & Enrichment Pipeline

## Business Context

Mid-market and enterprise B2B sales organisations routinely acquire prospect lists—event registrations, partner referrals, purchased lead files—with **company names only** and little or no firmographic structure. Revenue teams, SDRs, and account researchers must turn those names into usable account records (industry, approximate size, technology footprint, and contact hints) before outreach or CRM import.

The pain is acute in **high-volume outbound** and **territory planning**, where thousands of rows arrive at once and manual research does not scale.

## Current Manual Process

Typical steps per company name:

1. **Search** for the official website (search engine, LinkedIn, news).
2. **Open** the site and skim **About**, **Careers**, **Contact**, and sometimes **footer** text.
3. **Infer** industry and company size from wording, job titles, and office locations.
4. **Guess** tech stack from job postings, marketing pages, or built-with hints.
5. **Note** generic or role-based contacts (e.g. `info@`, `sales@`) where visible.
6. **Copy** findings into a spreadsheet or CRM.

**Time:** roughly **3–10 minutes per company** depending on ambiguity and researcher familiarity.

**Frequency:** during list drops or campaign prep, often **hundreds to thousands of rows per batch** (the project definition cites **~5,000 names** with no structured data).

## Pain Points

- **Throughput:** Manual research cannot clear large lists without a large team or long delays.
- **Consistency:** Different researchers tag industries and sizes differently; tech stack notes are ad hoc.
- **Error risk:** Wrong website, outdated size band, or hallucinated detail when rushing.
- **Key-person risk:** Tribal knowledge lives in senior reps; absence or turnover stalls enrichment.
- **Downstream friction:** CRM and sequencing tools need **structured fields**, not paragraphs of notes.

## Automation Opportunity

| Step | Automate | Human judgement |
|------|----------|-----------------|
| Resolve company → canonical website | Yes (with confidence score) | Override when brand collision or rebranding |
| Fetch and extract text from public pages | Yes | Policy on which pages are in scope |
| Classify industry, size band, tech themes | Yes (LLM + validation) | Review low-confidence or regulated sectors |
| Extract/surface contact channels | Yes (from scraped text only) | Compliance review for outreach use |
| Aggregate **data quality score** | Yes | Define thresholds for “ready to use” |

**Expected impact:** reduce **minutes per row to seconds** for the automated path; keep a **small review slice** for ambiguous cases without blocking the whole batch.

## Inputs

- **Primary input:** a list of **company names** (and optionally locale, country, or prior URL hints if provided later—out of scope unless added explicitly).
- **Format:** batch upload via API (e.g. JSON array or CSV) as defined in implementation; internal normalisation to a canonical `CompanyInput` record.
- **Volume:** design target **up to 5,000 companies per run** with configurable concurrency and cost limits.
- **Worst-case inputs:** ambiguous names (`“Acme”`, `“Vertex”`), non-English pages, parked domains, JavaScript-heavy sites with little static HTML, rate limits from external services.

## Outputs

- **Enriched records** per company, including at minimum (per project definition):

  - Industry (normalised label or taxonomy code—exact enum fixed in schema).
  - Size (structured band, e.g. employee range).
  - Tech stack (tags / categories, not unbounded free text only).
  - Contacts (channels found in scraped content—e.g. email patterns, contact page URLs—within policy).

- **Data quality score** per record (and components), suitable for filtering before CRM sync.

- **Auditability:** prompt version, model id, source URLs fetched, and correlation id for each pipeline step.

Downstream systems are not fixed in scope; deliver **API + exportable structured data** (JSON/CSV) so CRM or warehouse ingestion can be added later without changing the core definition.

## Failure Modes

| Failure | Mitigation |
|---------|------------|
| AI wrong or inconsistent | Schema validation, rule checks, composite quality score; low scores flagged |
| Wrong website chosen | Multi-signal discovery scoring; record `website_confidence`; failed discovery explicit |
| Site unreachable / blocked | Retries, circuit breaker, clear terminal state—not silent empty success |
| OpenAI outage or 429 | Backoff, limits, persisted failure reason; batch run remains resumable |
| Scraping legal/ToS concerns | Fetch only public marketing pages; configurable user-agent; rate limits; document runbook |

**Human fallback:** review or re-run specific rows; optional threshold-based queue (implementation may expose “needs review” without expanding scope to a full review UI unless planned in a later phase).

## Success Criteria

- **Functional:** For a batch of sample companies with known websites, the pipeline produces **schema-valid** enriched records and **non-trivial** quality scores.
- **Reliability:** A full run completes with **per-row terminal states** (success, partial, failed) and **resumable** batch tracking.
- **Observability:** Health, readiness, and metrics endpoints; structured logs with **correlation IDs**.
- **Cost/latency:** Documented **per-company cost and latency** targets in metrics (exact numbers tuned during implementation within OpenAI budget constraints).
- **Quality:** Evaluation harness on a **fixed test set** (mocked HTTP/LLM in CI; optional live eval locally) with reported accuracy/precision for key fields.

These criteria align with the portfolio standard: production-oriented behaviour, not demo-only happy paths.
