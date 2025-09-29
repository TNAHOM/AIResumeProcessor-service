# ATS Resume Parser Service (Python)

This repository contains a Python microservice used by an Applicant Tracking System (ATS) to parse resumes. The other microservices in the ATS are implemented in Go (Gin); this one is Python-based because it integrates AI tooling (Gemini, embeddings, etc.) and the Python ecosystem provides many resources and SDKs for those tasks.

The service exposes a FastAPI HTTP API to upload resumes (PDF). Uploaded resumes are stored in S3, processed asynchronously using AWS Textract, normalized with a Gemini-based service, and embedded for semantic search.

## Architecture Overview

The service has been migrated to use an **async Redis-based job queue** for improved throughput and scalability:

- **API Layer**: FastAPI endpoints accept resume uploads and return status
- **Job Queue**: Redis-powered queue replaces FastAPI's BackgroundTasks for better reliability
- **Async Workers**: Fully asynchronous background workers process resumes concurrently
- **Pipeline**: S3 → Textract → Grouping → Gemini → Embeddings → Database (all async)
- **Database**: Optimized with strategic indexes for high-frequency queries

### Job Processing Flow

1. **Upload** (`POST /resumes/upload`): Creates Application record, uploads to S3, enqueues job to Redis
2. **Background Processing**: Async worker picks up job from Redis queue and processes through the full pipeline
3. **Status Check** (`GET /resumes/{id}`): Returns current processing status and results

### Database Optimization

Recent performance improvements include strategic indexes on:
- `status` - Fast filtering by processing status
- `job_post_id` - Efficient foreign key lookups
- `created_at` - Temporal queries and sorting


## Folder structure

Top-level files and folders (high-level view):

- `alembic.ini` - Alembic configuration (may be gitignored in your workflow)
- `Readme.md` - This document
- `requirements.txt` - Python dependencies
- `app/`
  - `main.py` - FastAPI app entrypoint and health-check
  - `core/config.py` - configuration using Pydantic settings (env vars listed below)
  - `db/`
	- `models.py` - SQLAlchemy models (Application model, custom GUID type)
	- `session.py` - SQLAlchemy engine/session factory
  - `routers/`
	- `resumes.py` - `/resumes` endpoints (upload and status)
  - `schemas/` - Pydantic request/response schemas
  - `services/` - Business logic, Gemini and embedding integrations, Textract grouping
  - `workers/` - Background worker that performs the pipeline for an application
- `migrations/` - Alembic migration scripts (versioned)
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
- REDIS_URL - Redis connection URL (defaults to `redis://localhost:6379/0`)

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

3. Configure environment

	- Create a `.env` file (see example above).
	- Ensure the database referenced by `DB_URL` is accessible.

4. Run Redis (for background job processing)

	Using Docker:
	```
	docker-compose -f docker-compose.redis.yml up -d
	```
	
	Or install Redis natively and run:
	```
	redis-server
	```

5. Start background worker (async job processor)

	```
	python -m app.workers.redis_worker
	```

6. Run the API (development)

	```
	uvicorn app.main:app --reload
	```

The API will be available at http://127.0.0.1:8000 with automatic Swagger UI at http://127.0.0.1:8000/docs

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

## Background Job Processing

The service now uses Redis for reliable background job processing instead of FastAPI's built-in BackgroundTasks.

### Starting Redis

#### Option 1: Docker (Recommended)
```bash
docker-compose -f docker-compose.redis.yml up -d
```

#### Option 2: Native Redis Installation
Install Redis and run:
```bash
redis-server
```

### Starting the Async Worker

The async worker processes resume jobs from the Redis queue:

```bash
# From project root, with virtual environment activated
python -m app.workers.redis_worker
```

The worker will:
- Connect to Redis (falls back to MockRedis if unavailable)
- Poll for jobs every 5 seconds  
- Process resume uploads asynchronously through the full pipeline
- Handle errors gracefully and mark failed jobs appropriately

### Development Notes

- **Graceful Fallback**: If Redis is unavailable, the service uses MockRedis for development
- **Async Pipeline**: All I/O operations (S3, Textract, DB) run asynchronously for better throughput
- **Signal Handling**: Worker can be stopped gracefully with Ctrl+C (SIGINT/SIGTERM)
- **Error Handling**: Failed jobs are marked in the database with detailed error information

## Design & rationale

- Python was chosen for this microservice because the AI/ML integrations (Gemini, embeddings, and various SDKs) are often simpler to implement and maintain in Python. The rest of the ATS is in Go for performance-critical services.


## Contribution

- When changing models, create a new Alembic revision and commit the generated migration file(s) into `migrations/versions/`.
- Keep secrets out of the repo. Use environment variables or your team's secret manager.

---
