## Purpose

Short, actionable guidance for AI coding agents working on this repository: a FastAPI microservice that uploads resumes to S3, runs AWS Textract, normalizes results with Google Gemini, creates embeddings, and persists results in Postgres via SQLAlchemy.

## Architecture (overview)

- API: `app/main.py` boots FastAPI; routes live in `app/routers/resumes.py`.
- Persistence: SQLAlchemy models `app/db/models.py`; session/engine in `app/db/session.py`.
- Pipeline orchestration: `app/workers/resume_processor.py` executes S3 -> Textract -> grouping -> Gemini -> embed -> DB save.
- Business logic: `app/services/*` (S3 upload, Textract grouping, Gemini call, embeddings).

## Folders and key files

- `app/`
  - `main.py`: FastAPI app + health check; runs `models.Base.metadata.create_all(bind=engine)`.
  - `routers/resumes.py`: endpoints
    - POST `/resumes/upload` (accepts file, enqueues background job)
    - GET `/resumes/{application_id}` (returns processing status/data)
  - `schemas/`: response models (`schemas/resume.py`) and Gemini output schema (`schemas/gemini_output.py`).
  - `services/`: 
    - `resume_service.py`: S3 upload + background task creation.
    - `textract_grouper.py`: convert Textract LINE blocks into grouped text chunks.
    - `gemini_service.py`: prompt + strict JSON parsing to `ResumeOutput`.
    - `embeding_service.py`: embeddings via Gemini embedding model.
  - `workers/resume_processor.py`: Textract client, polling, grouping, Gemini, embeddings, DB writes with error handling.
  - `db/models.py`: `Application` model, statuses, custom `GUID` (UUID stored as string); `db/session.py`: engine + `get_db()`.
- `migrations/`: Alembic migration scripts exist, but note `.gitignore` ignores `alembic.ini` and `migrations/` (verify before adding new migrations).
- `scripts/`: helper/experimental scripts (not used by the running service; also ignored by `.gitignore`).
- `files/`, `result/`, `airesult/`: sample inputs/outputs.

## API flow (request → background job → status)

1) POST `/resumes/upload` (see `routers/resumes.py`)
   - Input: multipart file (PDF).
   - Behavior: creates `Application` row (status=QUEUED), uploads file to S3 path `resumes/{uuid}_{filename}`, enqueues `process_resume(application_id)` via `BackgroundTasks`.
   - Response (`schemas.ResumeCreateResponse`): `{ application_id: UUID, status, message }`.

2) Background pipeline (`workers/resume_processor.py`)
   - Textract StartDocumentAnalysis (LAYOUT, FORMS) → poll → collect all pages (`NextToken`).
   - Group LINE blocks (`services/textract_grouper.py::grouping`) → dict[str, list[str]].
   - Gemini JSON normalization (`services/gemini_service.py`) → must conform to `schemas/gemini_output.ResumeOutput`.
   - Create embedding (`services/embeding_service.py`) → store `embedded_value`.
   - Persist: `Application.extracted_data`, `embedded_value`, set status=COMPLETED (or FAILED with `failed_reason`).

3) GET `/resumes/{application_id}`
   - Response (`schemas.ResumeStatusResponse`): `{ id, original_filename, status, s3_path?, extracted_data?, created_at, updated_at? }`.

Statuses: `PENDING | QUEUED | PROCESSING | COMPLETED | FAILED` (see `db/models.py`).

## Dev workflow (Windows, cmd.exe)

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs (try POST /resumes/upload with a file from `files/`).

## Environment & secrets

Set via `app/core/config.py` (Pydantic). Create a `.env` in project root:
- DB_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION, AWS_S3_BUCKET_NAME, GEMINI_API_KEY
`.env` is ignored by Git.

## Contracts & data shapes

- Input to Gemini: grouped resume text mapping like `{ "1": ["..."], "2": ["..."] }` (keys sorted numerically before join).
- Output from Gemini: must match `schemas/gemini_output.py::ResumeOutput` (strict JSON only).
- DB id type: `GUID` TypeDecorator stores UUIDs as strings; reading returns `uuid.UUID` when possible.

## Project-specific gotchas

- create_all vs Alembic: app creates tables on startup, but migrations exist — prefer revising models + adding migrations. Note `.gitignore` ignores `alembic.ini` and `migrations/`; coordinate before generating/committing new migrations.
- Package mismatch risk: code imports `from google import genai` (new SDK), but `requirements.txt` lists `google-generativeai`. Ensure correct dependency (`google-genai`) or update imports to match installed SDK.
- Embedding input: `create_embedding` does `list(json_contents)` — passing a dict will iterate keys. Pass a list of text chunks or serialize/flatten before calling.
- Model default type: `Application.embedded_value` is JSON with default `{}` but stores `list[float]`; default should be `[]` to match shape (fix when editing models + migrations).
- UUID handling: when passing `application_id` to worker ensure it’s a `uuid.UUID` (see `resume_service.create_upload_job`). Query routes accept string ids; avoid type mismatches.
- Textract polling: handle `NextToken` pagination and timeouts (already implemented in `TextractService`).

## Where to change behavior

- Prompt/rules/schema strictness: `services/gemini_service.py` and `schemas/gemini_output.py`.
- Grouping heuristics: `services/textract_grouper.py`.
- Storage schema: `db/models.py` (+ add a migration under `migrations/versions/`).

## Quick pointers

- Upload flow trace: `routers/resumes.py` → `services/resume_service.py::create_upload_job` → `workers/resume_processor.py::process_resume`.
- Health check: GET `/` in `app/main.py`.

## Validation ideas (no tests yet)

- Smoke: upload a sample PDF and watch status move QUEUED → PROCESSING → COMPLETED.
- Unit: feed `result/raw_resume*.json` blocks to `textract_grouper.grouping` and assert structure.
