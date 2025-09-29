# ATS Resume Parser Service (Python)

This repository contains a Python microservice used by an Applicant Tracking System (ATS) to parse resumes. The other microservices in the ATS are implemented in Go (Gin); this one is Python-based because it integrates AI tooling (Gemini, embeddings, etc.) and the Python ecosystem provides many resources and SDKs for those tasks.

The service exposes a FastAPI HTTP API to upload resumes (PDF). Uploaded resumes are stored in S3, processed asynchronously using AWS Textract, normalized with a Gemini-based service, and embedded for semantic search.

## Quick overview

- Framework: FastAPI
- DB: SQLAlchemy (models in `app/db/models.py`)
- Migrations: Alembic (migration scripts live in `alembic/`)
- Background processing: Redis-powered job queue using Celery that performs Textract -> grouping -> Gemini -> embedding -> save flow
- Queue: Redis with Celery for asynchronous job processing
- Async Operations: Full async pipeline with improved throughput

## Folder structure

Top-level files and folders (high-level view):

- `alembic.ini` - Alembic configuration for database migrations
- `alembic/` - Alembic migration scripts and configuration
- `docker-compose.yml` - Docker services for Redis and PostgreSQL
- `worker.py` - Celery worker entry point
- `Readme.md` - This document
- `requirements.txt` - Python dependencies (includes Redis, Celery, async libraries)
- `app/`
  - `main.py` - FastAPI app entrypoint and health-check
  - `core/config.py` - configuration using Pydantic settings (env vars listed below)
  - `core/celery_app.py` - Celery application configuration
  - `db/`
	- `models.py` - SQLAlchemy models (Application model, custom GUID type) with optimized indexes
	- `session.py` - SQLAlchemy engine/session factory with async support
  - `routers/`
	- `resumes.py` - `/resumes` endpoints (upload and status) - now uses Redis queue
  - `schemas/` - Pydantic request/response schemas
  - `services/` - Business logic, Gemini and embedding integrations, Textract grouping, queue service
  - `workers/` - Background workers and tasks for the async pipeline

## Environment variables

The service loads settings via `app/core/config.py` using Pydantic's settings feature. Add a `.env` file in the project root (do not commit it) with the following variables:

- DB_URL - SQLAlchemy database URL, e.g. `postgresql://user:pass@host:5432/dbname`
- AWS_ACCESS_KEY_ID - AWS credential
- AWS_SECRET_ACCESS_KEY - AWS credential
- AWS_DEFAULT_REGION - AWS region (e.g., `us-east-1`)
- AWS_S3_BUCKET_NAME - S3 bucket name used for Textract input
- GEMINI_API_KEY - API key / token for Gemini
- REDIS_URL - Redis connection URL (e.g., `redis://localhost:6379/0`)

Example `.env` (local development):

```
DB_URL=postgresql://postgres:password@localhost:5432/resume_db
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
AWS_S3_BUCKET_NAME=my-resume-bucket
GEMINI_API_KEY=sk-xxx
REDIS_URL=redis://localhost:6379/0
```

## Setup (Windows - cmd.exe)

1. Create and activate a virtual environment

	python -m venv .venv
	.venv\Scripts\activate

2. Install dependencies

	pip install --upgrade pip
	pip install -r requirements.txt

3. Start required services using Docker

	docker-compose up -d

4. Configure environment

	- Create a `.env` file (see example above).
	- Ensure the database referenced by `DB_URL` is accessible.

5. Run database migrations

	alembic upgrade head

6. Run the API (development)

	uvicorn app.main:app --reload

7. Start the Celery worker (in a separate terminal)

	celery -A app.core.celery_app worker --loglevel=info

## Docker Development Setup

The project includes a `docker-compose.yml` file that provides Redis and PostgreSQL services for local development:

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f
```

Services provided:
- **Redis**: Available on `localhost:6379` for job queue
- **PostgreSQL**: Available on `localhost:5432` for database

## Celery Worker Management

The async processing pipeline uses Celery with Redis as the broker. To manage workers:

### Development
```bash
# Start a single worker
celery -A app.core.celery_app worker --loglevel=info

# Start worker with specific concurrency
celery -A app.core.celery_app worker --loglevel=info --concurrency=4

# Monitor tasks
celery -A app.core.celery_app flower
```

### Production
```bash
# Use the provided worker script
python worker.py

# Or use Celery directly with production settings
celery -A app.core.celery_app worker --loglevel=warn --concurrency=8
```

## Alembic (migrations)

Database migrations are managed with Alembic. The configuration is already set up to use your application settings.

1. Generate a migration after changing models:

	alembic revision --autogenerate -m "describe change"

2. Apply migrations:

	alembic upgrade head

3. View migration history:

	alembic history

4. Rollback to specific revision:

	alembic downgrade <revision>

**Migration files are committed to the repository** in `alembic/versions/` so all developers and CI can apply the same database schema changes.

## Database Indexing

The Application model includes optimized indexes for common query patterns:

- `id` (primary key, automatic)
- `s3_path` (unique index for S3 file lookups)
- `status` (index for filtering by processing status)
- `email` (index for applicant lookups)
- `job_post_id` (index for filtering by job post)
- `created_at` (index for date-based sorting and filtering)

These indexes significantly improve query performance for:
- Status lookups (`/resumes/{id}` endpoint)
- Filtering applications by status, email, or job post
- Date-based queries and sorting

## Testing / Smoke test

- Start the API and Redis: `docker-compose up -d && uvicorn app.main:app --reload`
- Start the worker: `celery -A app.core.celery_app worker --loglevel=info`
- Use `/resumes/upload` in the Swagger UI and upload a sample PDF from `files/` to ensure the upload route accepts files and creates an Application entry in the DB.
- Check Redis queue: jobs should be enqueued and processed by the worker
- Monitor processing: application status should transition from QUEUED -> PROCESSING -> COMPLETED

## API Flow (Redis Queue)

1) POST `/resumes/upload` (see `routers/resumes.py`)
   - Input: multipart file (PDF).
   - Behavior: creates `Application` row (status=QUEUED), uploads file to S3 path `resumes/{uuid}_{filename}`, enqueues async processing job via Redis/Celery.
   - Response (`schemas.ResumeCreateResponse`): `{ application_id: UUID, status, message }`.

2) Background pipeline (`workers/async_resume_processor.py` via Celery task)
   - Textract StartDocumentAnalysis (LAYOUT, FORMS) → async poll → collect all pages (`NextToken`).
   - Group LINE blocks (`services/textract_grouper.py::grouping`) → dict[str, list[str]].
   - Gemini JSON normalization (`services/gemini_service.py`) → must conform to `schemas/gemini_output.ResumeOutput`.
   - Create embedding (`services/embeding_service.py`) → store `embedded_value`.
   - Persist: `Application.extracted_data`, `embedded_value`, set status=COMPLETED (or FAILED with `failed_reason`).

3) GET `/resumes/{application_id}`
   - Response (`schemas.ResumeStatusResponse`): `{ id, original_filename, status, s3_path?, extracted_data?, created_at, updated_at? }`.

Statuses: `PENDING | QUEUED | PROCESSING | COMPLETED | FAILED` (see `db/models.py`).

## Performance Improvements

### Async Processing
- Full async pipeline with `async/await` throughout
- Async database operations using SQLAlchemy async engine
- Async AWS services (S3, Textract) using aioboto3
- Async Gemini API calls with executor threads

### Redis Job Queue
- Replaced FastAPI BackgroundTasks with Redis/Celery
- Persistent job queue survives application restarts
- Job retry logic with exponential backoff
- Distributed processing across multiple workers

### Database Indexing
- Strategic indexes on high-frequency query columns
- Improved performance for status lookups and filtering
- Optimized for common application lifecycle queries

## Design & rationale

- Python was chosen for this microservice because the AI/ML integrations (Gemini, embeddings, and various SDKs) are often simpler to implement and maintain in Python. The rest of the ATS is in Go for performance-critical services.
- Redis queue provides reliable, persistent job processing that scales horizontally
- Async processing improves throughput and resource utilization
- Strategic database indexing optimizes query performance for common patterns

## Contribution

- When changing models, create a new Alembic revision and commit the generated migration file(s) into `alembic/versions/`.
- Keep secrets out of the repo. Use environment variables or your team's secret manager.
- Test both sync and async code paths when making changes to the processing pipeline.
- Monitor Redis queue health and worker performance in production.

---
