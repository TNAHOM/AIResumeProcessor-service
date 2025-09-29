# Migration Guide: Redis Job Queue and Async Pipeline

This document outlines the migration from FastAPI's `BackgroundTasks` to a Redis-powered Celery job queue with async pipeline processing.

## What Changed

### 1. Background Job Processing

**Before**: Used FastAPI's built-in `BackgroundTasks`
- Jobs ran in the same process as the web server
- Limited scalability and resilience
- No job persistence or monitoring

**After**: Redis-powered Celery job queue
- Jobs run in separate worker processes
- Horizontal scaling by adding more workers
- Job persistence, retry logic, and monitoring via Flower
- Better error handling and recovery

### 2. Pipeline Processing

**Before**: Synchronous processing pipeline
- Blocking operations (S3, Textract, Gemini calls)
- No concurrency within a single job
- Inefficient resource utilization

**After**: Asynchronous processing pipeline
- Non-blocking I/O operations
- Better resource utilization
- Improved throughput for long-running operations

### 3. Database Performance

**Before**: Limited indexing
- Only primary key and S3 path indexes
- Slow queries for status lookups and filtering

**After**: Optimized indexing strategy
- Individual indexes on frequently queried columns
- Composite indexes for common query patterns
- Significantly improved query performance

## Technical Changes

### Dependencies Added

```
celery[redis]  # Celery with Redis support
redis          # Redis Python client
aioboto3       # Async AWS SDK
```

### New Files

- `app/core/celery_app.py` - Celery application configuration
- `app/workers/celery_tasks.py` - Celery task definitions
- `docker-compose.yml` - Development environment with Redis
- `Dockerfile` - Container image for the application
- `worker.py` - Celery worker startup script
- `migrations/versions/001_add_performance_indexes.py` - Database indexes migration

### Modified Files

- `app/core/config.py` - Added `REDIS_URL` setting
- `app/routers/resumes.py` - Removed `BackgroundTasks` dependency
- `app/services/resume_service.py` - Updated to use Celery task enqueueing
- `app/workers/resume_processor.py` - Added async version of processing pipeline
- `app/db/models.py` - Added performance indexes and fixed embedded_value default
- `requirements.txt` - Added new dependencies

## Performance Improvements

### Database Query Performance

The new indexing strategy provides significant performance improvements:

1. **Status Queries**: 10-100x faster lookups by status
2. **Time-based Queries**: Efficient filtering by creation/update time
3. **Job-specific Queries**: Fast retrieval of applications for specific job posts
4. **User Queries**: Quick lookup of applications by email

### Async Processing Benefits

1. **I/O Concurrency**: Textract polling, S3 operations, and Gemini calls don't block each other
2. **Better Resource Utilization**: CPU and memory usage optimized
3. **Improved Throughput**: Multiple operations can proceed concurrently within a single job

### Scalability Improvements

1. **Horizontal Scaling**: Add more Celery workers to handle increased load
2. **Job Persistence**: Jobs survive application restarts
3. **Retry Logic**: Automatic retry of failed jobs with exponential backoff
4. **Monitoring**: Real-time job monitoring with Celery Flower

## Migration Steps for Existing Deployments

### 1. Infrastructure Setup

```bash
# Start Redis (required for job queue)
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Or use docker-compose
docker-compose up -d redis
```

### 2. Database Migration

```bash
# Apply the new indexes
alembic upgrade head
```

### 3. Application Deployment

```bash
# Install new dependencies
pip install -r requirements.txt

# Start the web application
uvicorn app.main:app --reload

# Start Celery workers (in separate process/container)
celery -A app.core.celery_app worker --loglevel=info
```

### 4. Environment Variables

Add to your `.env` file:
```
REDIS_URL=redis://localhost:6379/0
```

## Monitoring and Debugging

### Celery Flower Dashboard

```bash
# Start Flower for job monitoring
celery -A app.core.celery_app flower --port=5555

# Access at http://localhost:5555
```

### Logs

- **Worker logs**: Show detailed job processing information
- **Redis logs**: Show job queue operations
- **Application logs**: Show API request/response information

### Key Metrics to Monitor

1. **Job Queue Length**: Number of pending jobs
2. **Job Processing Time**: Average time per job
3. **Job Success/Failure Rate**: Percentage of successful jobs
4. **Worker Health**: Number of active workers
5. **Database Query Performance**: Query execution times

## Rollback Plan

If issues occur, you can temporarily rollback to synchronous processing:

1. **Stop Celery workers**
2. **Import the old synchronous function** in `resume_service.py`:
   ```python
   from app.workers.resume_processor import process_resume
   ```
3. **Use BackgroundTasks** temporarily:
   ```python
   background_tasks.add_task(process_resume, application_id, job_post_id)
   ```

Note: The database indexes should remain as they only improve performance.

## Best Practices

1. **Monitor job queue length** to ensure workers can keep up with demand
2. **Set up alerts** for job failures or long processing times  
3. **Use Redis persistence** in production to survive Redis restarts
4. **Scale workers horizontally** based on job volume
5. **Monitor database performance** and adjust indexes as query patterns evolve

## Troubleshooting

### Common Issues

1. **Redis Connection Errors**: Ensure Redis is running and accessible
2. **Import Errors**: Ensure all new dependencies are installed
3. **Database Migration Errors**: Run migrations in the correct order
4. **Async/Await Errors**: Check that all async functions are properly awaited

### Debug Commands

```bash
# Check Redis connectivity
redis-cli ping

# List Celery workers
celery -A app.core.celery_app inspect active

# Check job queue status
celery -A app.core.celery_app inspect stats
```