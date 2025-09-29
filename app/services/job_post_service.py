from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, Dict, Any


def get_job_post_by_id(db: Session, job_post_id) -> Optional[Dict[str, Any]]:
    """Synchronous version - get job post by ID."""
    result = db.execute(
        text("SELECT * FROM job_posts WHERE id = :id"), {"id": job_post_id}
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def get_job_post_by_id_async(job_post_id) -> Optional[Dict[str, Any]]:
    """Async version - get job post by ID."""
    # For now, return a mock job post since we don't have job_posts table
    # In production, this would query the actual job_posts table
    return {
        "id": job_post_id,
        "title": "Software Engineer",
        "description": "We are looking for a skilled software engineer...",
        "requirements": "Bachelor's degree in Computer Science or related field...",
        "responsibilities": "Develop and maintain software applications...",
        "description_embedding": [0.1] * 3072,  # Mock embedding
        "requirements_embedding": [0.2] * 3072,  # Mock embedding
        "responsibilities_embedding": [0.3] * 3072,  # Mock embedding
    }
