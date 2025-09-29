# ATS Resume Parser Service (Python)

This repository contains a Python microservice used by an Applicant Tracking System (ATS) to parse resumes. The other microservices in the ATS are implemented in Go (Gin); this one is Python-based because it integrates AI tooling (Gemini, embeddings, etc.) and the Python ecosystem provides many resources and SDKs for those tasks.

The service exposes a FastAPI HTTP API to upload resumes (PDF). Uploaded resumes are stored in S3, processed asynchronously using AWS Textract, normalized with a Gemini-based service, and embedded for semantic search.

## Quick overview

- Framework: FastAPI
- DB: SQLAlchemy (models in `app/db/models.py`)
- Migrations: Alembic (migration scripts live in `migrations/`)
- Background processing: **Redis-powered Celery workers** perform Textract -> grouping -> Gemini -> embedding -> save flow
- Job queue: **Redis** with **Celery** for scalable async processing

## Folder structure

Top-level files and folders (high-level view):

- `alembic.ini` - Alembic configuration (may be gitignored in your workflow)
- `docker-compose.yml` - Docker setup for Redis, PostgreSQL, and Celery workers
- `Dockerfile` - Container image for the application
- `worker.py` - Celery worker startup script
- `Readme.md` - This document
- `requirements.txt` - Python dependencies
- `app/`
  - `main.py` - FastAPI app entrypoint and health-check
  - `core/`
    - `config.py` - configuration using Pydantic settings (env vars listed below)
    - `celery_app.py` - Celery app configuration
  - `db/`
	- `models.py` - SQLAlchemy models (Application model, custom GUID type, optimized indexes)
	- `session.py` - SQLAlchemy engine/session factory
  - `routers/`
	- `resumes.py` - `/resumes` endpoints (upload and status) - **now uses Celery**
  - `schemas/` - Pydantic request/response schemas
  - `services/` - Business logic, Gemini and embedding integrations, Textract grouping
  - `workers/` 
    - `resume_processor.py` - **Async** background worker that performs the pipeline for an application
    - `celery_tasks.py` - Celery task definitions
- `migrations/` - Alembic migration scripts (versioned) - **includes performance indexes**
- `scripts/` - helper scripts (Textract helpers, embedding scripts, formatting, experiments)
- `files/`, `result/`, `airesult/` - sample input PDFs and example outputs

Refer to the project tree in your editor for the full file list.

## Environment variables

The service loads settings via `app/core/config.py` using Pydantic's settings feature. Add a `.env` file in the project root (do not commit it) with the following variables:

- DB_URL - SQLAlchemy database URL, e.g. `postgresql://user:pass@host:5432/dbname`
- AWS_ACCESS_KEY_ID - AWS credential
- AWS_SECRET_ACCESS_KEY - AWS credential
- AWS_DEFAULT_REGION - AWS region (e.g., `us-east-1`)
- AWS_S3_BUCKET_NAME - S3 bucket name used for Textract input
- GEMINI_API_KEY - API key / token for Gemini
- **REDIS_URL** - Redis URL for job queue, e.g. `redis://localhost:6379/0`

Example `.env` (local development):

DB_URL=postgresql://postgres:password@localhost:5432/resume_db
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
AWS_S3_BUCKET_NAME=my-resume-bucket
GEMINI_API_KEY=sk-xxx
REDIS_URL=redis://localhost:6379/0

## Setup Options

### Option 1: Docker Development Environment (Recommended)

The easiest way to get started is using Docker Compose, which provides Redis, PostgreSQL, and Celery workers:

1. **Copy environment template**
   ```bash
   cp .env.example .env
   # Edit .env with your actual AWS and Gemini credentials
   ```

2. **Start services**
   ```bash
   # Start Redis and PostgreSQL
   docker-compose up -d redis postgres
   
   # Run migrations (first time only)
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   alembic upgrade head
   
   # Start the FastAPI application
   uvicorn app.main:app --reload
   
   # In another terminal, start the Celery worker
   celery -A app.core.celery_app worker --loglevel=info
   ```

3. **Optional: Monitor jobs with Flower**
   ```bash
   docker-compose --profile monitoring up flower
   # Access at http://localhost:5555
   ```

### Option 2: Manual Setup (Windows - cmd.exe)

1. **Install and start Redis locally**
   - Download Redis from https://redis.io/download or use WSL
   - Start Redis server: `redis-server`

2. **Create and activate a virtual environment**
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```cmd
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment**
   - Create a `.env` file (see example above).
   - Ensure the database referenced by `DB_URL` is accessible.
   - Ensure Redis is running at `REDIS_URL`.

5. **Run database migrations**
   ```cmd
   alembic upgrade head
   ```

6. **Start the FastAPI application**
   ```cmd
   uvicorn app.main:app --reload
   ```

7. **Start the Celery worker** (in a separate terminal)
   ```cmd
   .venv\Scripts\activate
   celery -A app.core.celery_app worker --loglevel=info
   ```

## Database Indexing and Performance

This version includes optimized database indexes for common query patterns:

- **Individual indexes**: `status`, `job_post_id`, `created_at`, `updated_at`
- **Composite indexes**: 
  - `(status, created_at)` - for dashboard queries filtering by status and time
  - `(job_post_id, status)` - for job-specific application queries
  - `(email, status)` - for user-specific queries

These indexes significantly improve performance for:
- Status lookups (`/resumes/{id}` endpoint)
- Filtering applications by status
- Time-based queries for reporting
- Job-specific application listings

## Migration Commands

Run migrations when the database schema changes:

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "Description of changes"
```

## Alembic (migrations) — guideline when `alembic.ini` is gitignored

If you plan to gitignore `alembic.ini` (common when different developers/CI systems have different DB URLs), here is a recommended local workflow to manage migrations:

1. Install Alembic if you don't have it:

	pip install alembic

2. Initialize a local Alembic environment (first time only). Run this in the project root. This creates a new folder and local `alembic.ini`:

	alembic init

3. Configure Alembic to use the application's settings. Edit `migra/env.py` and set the sqlalchemy.url from the app settings (recommended):

	from app.core.config import settings
	config.set_main_option('sqlalchemy.url', settings.settings.DB_URL)

4. Generate a migration after changing models:

	alembic -c alembic_local/alembic.ini revision --autogenerate -m "describe change"

5. Apply migrations:

	alembic -c alembic.ini upgrade head

6. Commit the generated migration file(s) from `migrations/versions/` (or your `alembic_local/versions/`) to the repository so other developers and CI can apply the same history. Even when `alembic.ini` is local and ignored, migration scripts should be version-controlled.

Notes:

- You can call Alembic with `-x` or environment variables if you prefer to pass the DB URL at runtime. Example: `alembic -c alembic_local/alembic.ini -x db_url=%DB_URL% upgrade head` (you'd need to adapt `env.py` to read `context.get_x_argument()`)
- Keep `migrations/versions/` committed — the migration scripts are what matter for repo reproducibility.

## Testing / Smoke test

- Start the API
- Use `/resumes/upload` in the Swagger UI and upload a sample PDF from `files/` to ensure the upload route accepts files and creates an Application entry in the DB.

## Design & rationale

- Python was chosen for this microservice because the AI/ML integrations (Gemini, embeddings, and various SDKs) are often simpler to implement and maintain in Python. The rest of the ATS is in Go for performance-critical services.


## Contribution

- When changing models, create a new Alembic revision and commit the generated migration file(s) into `migrations/versions/`.
- Keep secrets out of the repo. Use environment variables or your team's secret manager.

---
