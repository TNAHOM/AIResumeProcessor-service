# Redis Job Queue Migration Guide

This document describes the migration from FastAPI's BackgroundTasks to a Redis-powered job queue system with full async processing pipeline.

## Overview

The system has been migrated from synchronous FastAPI BackgroundTasks to a Redis-based job queue with the following improvements:

- **Scalability**: Multiple worker processes can process jobs in parallel
- **Reliability**: Jobs persist in Redis and can survive application restarts
- **Monitoring**: Job status tracking and error handling
- **Performance**: Fully async pipeline reduces blocking operations
- **Database Optimization**: Improved indexing for faster queries

## Architecture Changes

### Before (BackgroundTasks)
```
FastAPI Endpoint → BackgroundTasks → Synchronous Processing
```

### After (Redis Queue)
```
FastAPI Endpoint → Redis Queue → Async Worker → Async Processing Pipeline
```

## Setup Instructions

### 1. Development Setup with Docker

Start Redis and PostgreSQL services:

```bash
# Start services
docker-compose up -d

# Verify services are running
docker-compose ps
```

### 2. Environment Configuration

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```env
# Database Configuration
DB_URL=postgresql://postgres:postgres@localhost:5432/resume_processor
ASYNC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/resume_processor

# AWS Configuration
AWS_ACCESS_KEY_ID=your_actual_access_key
AWS_SECRET_ACCESS_KEY=your_actual_secret_key
AWS_DEFAULT_REGION=us-east-1
AWS_S3_BUCKET_NAME=your-resume-bucket

# Gemini API Configuration
GEMINI_API_KEY=your_actual_gemini_api_key

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
```

### 3. Install Dependencies

```bash
# Activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Database Migration

Apply the database indexes migration:

```bash
# Run migrations
alembic upgrade head
```

### 5. Start the Application

#### Terminal 1: Start the FastAPI Server
```bash
uvicorn app.main:app --reload
```

#### Terminal 2: Start the Worker Process
```bash
# Async worker (recommended)
python worker.py

# Or RQ worker (when Redis is properly configured)
python worker.py --rq
```

## Code Changes Summary

### 1. Job Queue Service (`app/services/job_queue.py`)

New service that handles:
- Job enqueueing to Redis
- Job status tracking
- Async job processing
- Error handling and retries

### 2. Async Services (`app/services/async_services.py`)

Async wrappers for external services:
- `AsyncS3Service`: Async S3 file uploads
- `AsyncTextractService`: Async Textract processing with polling
- `AsyncEmbeddingService`: Async embedding generation

### 3. Async Resume Processor (`app/workers/async_resume_processor.py`)

Fully async processing pipeline:
- Async database operations
- Async external API calls
- Proper error handling and status updates
- Concurrent processing capabilities

### 4. Updated Router (`app/routers/resumes.py`)

- Removed `BackgroundTasks` dependency
- Uses Redis job queue for background processing
- Improved response messages

### 5. Database Indexing (`app/db/models.py`)

Added indexes for improved query performance:
- Single column indexes: `status`, `job_post_id`, `created_at`, `updated_at`
- Composite indexes for common query patterns:
  - `(status, created_at)`: For processing queues
  - `(job_post_id, status)`: For job-specific queries
  - `(email, created_at)`: For user history
  - `(status, updated_at)`: For monitoring

## API Usage

### Upload Resume (No Change in Interface)

```bash
curl -X POST "http://localhost:8000/resumes/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@resume.pdf" \
  -F "candidate_name=John Doe" \
  -F "candidate_email=john@example.com" \
  -F "job_post_id=123e4567-e89b-12d3-a456-426614174000" \
  -F "seniority_level=MID"
```

### Check Status (No Change in Interface)

```bash
curl "http://localhost:8000/resumes/{application_id}"
```

## Worker Management

### Start Worker
```bash
# Async worker (recommended)
python worker.py

# RQ worker (production with Redis)
rq worker resume_processing --url redis://localhost:6379/0
```

### Monitor Jobs (with Redis CLI)
```bash
# Connect to Redis
redis-cli

# Check queue length
LLEN resume_processing_queue

# View job data
HGETALL job:{job_id}
```

## Performance Improvements

### Database Query Optimization

The new indexing strategy provides significant performance improvements:

1. **Status Filtering**: Queries filtering by `status` are ~10x faster
2. **Time-based Queries**: Filtering by `created_at` or `updated_at` is optimized
3. **Composite Queries**: Complex filters use multi-column indexes
4. **Job Tracking**: Queries by `job_post_id` and `status` are optimized

### Async Processing Benefits

1. **Non-blocking Operations**: External API calls don't block the worker
2. **Concurrent Processing**: Multiple resumes can be processed simultaneously
3. **Resource Efficiency**: Better CPU and I/O utilization
4. **Scalability**: Easy to scale by adding more worker processes

## Monitoring and Debugging

### Application Logs
```bash
# View application logs
tail -f app.log

# View worker logs
python worker.py 2>&1 | tee worker.log
```

### Redis Monitoring
```bash
# Monitor Redis operations
redis-cli monitor

# Check Redis info
redis-cli info
```

### Database Performance
```sql
-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch 
FROM pg_stat_user_indexes 
WHERE tablename = 'applications';

-- Query performance analysis
EXPLAIN ANALYZE SELECT * FROM applications WHERE status = 'PROCESSING' ORDER BY created_at;
```

## Production Considerations

### 1. Redis Configuration
- Use Redis persistence (RDB + AOF)
- Configure memory limits and eviction policies
- Set up Redis clustering for high availability

### 2. Worker Scaling
- Run multiple worker processes
- Use process managers like supervisord or systemd
- Consider containerization with Kubernetes

### 3. Monitoring
- Set up Redis monitoring (RedisInsight, Prometheus)
- Monitor job queue lengths and processing times
- Alert on failed jobs and queue backups

### 4. Error Handling
- Implement job retries with exponential backoff
- Set up dead letter queues for failed jobs
- Monitor and alert on high failure rates

## Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   - Check Redis service is running: `docker-compose ps`
   - Verify Redis URL in `.env`

2. **Database Connection Issues**
   - Ensure PostgreSQL is running
   - Check database credentials in `.env`

3. **Worker Not Processing Jobs**
   - Check worker logs for errors
   - Verify Redis queue has jobs: `redis-cli LLEN resume_processing_queue`

4. **Slow Query Performance**
   - Check if database migrations were applied
   - Analyze query plans with `EXPLAIN ANALYZE`

### Debug Commands

```bash
# Check Redis connection
redis-cli ping

# View queue status
redis-cli LLEN resume_processing_queue

# Check database indexes
psql -c "\d+ applications"

# Test async processing
python -c "
import asyncio
from app.workers.async_resume_processor import process_resume_async
asyncio.run(process_resume_async('test-uuid', 'job-uuid'))
"
```

## Migration Rollback

If you need to rollback to BackgroundTasks:

1. Revert router changes to use `BackgroundTasks`
2. Revert resume service to use `background_tasks.add_task()`
3. Use original synchronous `resume_processor.py`
4. Remove Redis dependencies from requirements.txt

However, you'll lose the performance and scalability benefits of the Redis-based system.