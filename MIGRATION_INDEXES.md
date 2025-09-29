# Database Index Migration

## Overview
This document describes the database indexing optimization implemented to improve query performance for resume applications.

## New Indexes Added

The following indexes have been added to the `applications` table for performance optimization:

### 1. Status Index
- **Column**: `status`
- **Purpose**: Fast filtering by processing status (PENDING, QUEUED, PROCESSING, COMPLETED, FAILED)
- **Impact**: Significantly improves queries that filter applications by status
- **Query Examples**: 
  ```sql
  SELECT * FROM applications WHERE status = 'COMPLETED';
  SELECT COUNT(*) FROM applications WHERE status IN ('PROCESSING', 'QUEUED');
  ```

### 2. Job Post ID Index  
- **Column**: `job_post_id`
- **Purpose**: Efficient foreign key lookups and filtering by job post
- **Impact**: Improves queries that join or filter by job post relationship
- **Query Examples**:
  ```sql
  SELECT * FROM applications WHERE job_post_id = 'uuid-here';
  SELECT COUNT(*) FROM applications WHERE job_post_id IS NOT NULL;
  ```

### 3. Created At Index
- **Column**: `created_at` 
- **Purpose**: Temporal queries and sorting by creation date
- **Impact**: Faster date-based filtering and ordering operations
- **Query Examples**:
  ```sql
  SELECT * FROM applications ORDER BY created_at DESC LIMIT 10;
  SELECT * FROM applications WHERE created_at >= '2024-01-01';
  ```

## Migration Information

### Alembic Migration
- **Migration ID**: `f5faddec4c43`
- **File**: `migrations/versions/f5faddec4c43_add_indexes_for_status_job_post_id_and_.py`
- **Description**: Add indexes for status, job_post_id, and created_at

### Running the Migration

```bash
# Apply the migration to add indexes
alembic upgrade head

# Rollback the migration if needed
alembic downgrade -1
```

**Note**: Migration files are in `migrations/` directory but may be `.gitignore`d per project policy. The migration script is documented here for reference.

## Performance Impact

### Before Optimization
- Status filtering: Table scan on all applications
- Job post filtering: Table scan for foreign key lookups  
- Date sorting: Full table sort without index

### After Optimization  
- Status filtering: Index scan (O(log n) lookup)
- Job post filtering: Index scan for fast foreign key resolution
- Date sorting: Index-based ordering (much faster)

### Expected Improvements
- **Status queries**: 10-100x faster depending on table size
- **Job post queries**: 5-50x faster for relationship lookups
- **Date-based queries**: 5-20x faster for temporal filtering and sorting

## Model Updates

The SQLAlchemy model has been updated to reflect the new indexes:

```python
class Application(Base):
    # ... other fields ...
    
    job_post_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)
    
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False, index=True
    )
    
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
```

## Monitoring

After applying the migration, monitor:
- Query execution times for status-based filtering
- Performance of job post relationship queries  
- Date-based sorting operations

Use `EXPLAIN ANALYZE` to verify index usage:
```sql
EXPLAIN ANALYZE SELECT * FROM applications WHERE status = 'COMPLETED';
```

Should show "Index Scan" instead of "Seq Scan" for optimal performance.