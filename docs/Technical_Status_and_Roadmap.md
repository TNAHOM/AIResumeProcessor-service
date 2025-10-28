## Technical Status and Roadmap (Chronological)

Updated: 2025-10-24

This document tracks what’s implemented, what to add, what to enhance, and what’s planned next for the AI Resume Processor service. It’s organized from past to future so you can follow the project’s progression at a glance.

## Phase 0 — Foundations (Completed)

- Project scaffold with FastAPI microservice
	- `app/main.py` initializes FastAPI and provides a health check
	- SQLAlchemy integration and table creation on startup
- Persistence setup
	- Models in `app/db/models.py` (Application model with statuses)
	- DB engine + session in `app/db/session.py`
	- Initial Alembic migration history in `migrations/`
- Configuration via Pydantic settings
	- `app/core/config.py` reads `.env` (DB_URL, AWS creds, S3 bucket, GEMINI_API_KEY)
- API routing scaffold
	- `app/routers/resumes.py` with endpoints stubbed for upload + status lookup
- Basic developer UX
	- `requirements.txt` for dependencies
	- Sample inputs/outputs in `files/`, `result/`, `airesult/`

Status: Implemented and working as the base to build on.

## Phase 1 — MVP Pipeline (Completed)

- Resume upload endpoint: POST `/resumes/upload`
	- Accepts PDF, creates `Application` row (status QUEUED)
	- Uploads file to S3 path `resumes/{uuid}_{filename}`
	- Enqueues background job via `BackgroundTasks`
- Background processing worker
	- Orchestration in `app/workers/resume_processor.py`
	- AWS Textract StartDocumentAnalysis + polling + pagination handling
	- Grouping of Textract LINE blocks in `services/textract_grouper.py`
	- Gemini normalization to strict JSON (`schemas/gemini_output.py::ResumeOutput`) in `services/gemini_service.py`
	- Embedding creation via Gemini in `services/embeding_service.py`
	- Persistence of `extracted_data`, `embedded_value`, status transitions, and errors
- Status endpoint: GET `/resumes/{application_id}`
	- Returns application metadata, status, and any extracted data if ready

Status: End-to-end flow operational for basic PDF resumes.

## Phase 2 — Stabilization and Reliability (In Progress / Next Up)

Focus: Fix known pitfalls, ensure consistent behavior, and reduce operational friction.

Immediate tasks to add or enhance:
- Dependency alignment
	- Ensure Google SDK imports match installed package
		- Code uses `from google import genai` (new SDK) → install `google-genai`
		- Alternatively, change imports to `google.generativeai` if using `google-generativeai`
- Embedding data shape consistency
	- `Application.embedded_value` stores `list[float]` — set SQLAlchemy default to `[]` (currently `{}` in some revisions)
	- Confirm migrations reflect this correction
- Embedding input correctness
	- `create_embedding` currently does `list(json_contents)`; passing a dict will iterate keys
	- Normalize embedding input to a flattened list of strings or serialized text chunks
- UUID handling
	- Ensure `application_id` passed into workers is a `uuid.UUID`, not a string
	- Confirm request parsing in routes matches DB model type
- Textract polling robustness
	- Confirm handling of `NextToken` pagination and reasonable timeouts/backoff
- Error transparency
	- Ensure `failed_reason` is set and propagated to GET response when failures occur
- Migrations hygiene
	- Prefer Alembic migrations over `create_all` for schema changes
	- Review `migrations/versions` to avoid drift with current models

Deliverable: A stable MVP with consistent types, correct embeddings, and clear errors.

## Phase 3 — Product Enhancements (Short Term)

What to add:
- Validation and tests
	- Unit tests for `textract_grouper`, `gemini_service` JSON parsing, and `embeding_service`
	- Integration test for upload → process → completed status
- Observability
	- Structured logging and correlation IDs per `application_id`
	- Basic metrics: job durations, success/failure rates, Textract/Gemini latencies
- Retry and resilience
	- Bounded retries for transient AWS/Gemini errors; dead-letter logging on exhaustion
	- Timeouts and circuit breakers for external calls
- Input constraints and safety
	- File size/type validation; graceful errors for unsupported inputs
	- Optional content redaction for PII in logs
- Developer ergonomics
	- Makefile/tasks or scripts for local run, lint, test, and migrate
	- Local docker-compose for Postgres and a MinIO/S3-compatible store

Deliverable: A safer, observable service with tests and improved DX.

## Phase 4 — Quality, Performance, and UX (Mid Term)

What to enhance:
- Prompting and schema strictness
	- Strengthen Gemini instructions; add JSON schema validation and fallbacks
	- Keep `schemas/gemini_output.py` canonical and versioned
- Embedding and search quality
	- Add `services/similarity_search.py` integration end-to-end; evaluate top-k results
	- Consider chunking strategies (overlap, semantic splitting) and model selection
- Data model evolution
	- Normalize key fields (name, email, skills) into structured columns for querying
	- Add indexing for frequent lookups
- API ergonomics
	- Pagination and filtering for listing processed applications
	- Webhook or callback support on completion
- Cost controls
	- Cache Gemini results where safe; deduplicate reprocessing for identical inputs

Deliverable: Higher-quality outputs, faster responses, and better API ergonomics.

## Phase 5 — Scale and Security (Longer Term)

Future items to implement:
- Asynchronous job system
	- Move background jobs to a real queue (e.g., Celery/RQ/Arq/BullMQ) with separate worker
	- Horizontal scaling and visibility into work-in-progress
- Multi-tenant and auth
	- Authentication/authorization for endpoints; rate limits per client
	- Tenant-aware S3 prefixes and database scoping
- Compliance and security
	- Secrets management (e.g., AWS Secrets Manager)
	- Audit logs and data retention policies
- Advanced retrieval
	- Store embeddings in a vector DB (e.g., pgvector, Qdrant, Pinecone)
	- Semantic search endpoints across processed resumes
- Document diversity
	- Support images, DOCX, and multi-file applications; automatic conversion to PDF as needed

Deliverable: Production-grade platform ready for external users and scale.

## Known Risks and Open Questions

- Package mismatch between import paths and installed Google SDK
- Schema drift risk between models and migrations
- Gemini output variability if prompts aren’t sufficiently constrained
- Embedding cost/latency as volume grows — consider batching and caching
- How strict should the JSON contract be vs. graceful degradation?

## Validation Checklist (Quick Wins)

- Upload a sample PDF from `files/` and verify status flows QUEUED → PROCESSING → COMPLETED
- Inspect `extracted_data` vs. `schemas/gemini_output.py::ResumeOutput` for conformance
- Confirm `embedded_value` is a list of floats and non-empty for successful runs
- Induce an error (bad AWS creds) and verify `failed_reason` appears in status response

## Changelog (High Level)

- Initial FastAPI + SQLAlchemy scaffold and routes
- End-to-end pipeline: S3 → Textract → Group → Gemini → Embedding → DB
- Iterative migrations to refine Application schema (IDs, s3_path, embedded values, failure reason)

---

If you need this condensed to a one-pager or converted into GitHub issues/milestones, say the word and we’ll auto-generate them.

