from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any


def get_job_post_by_id(db: Session, job_post_id) -> Optional[Dict[str, Any]]:
    result = db.execute(
        text("SELECT * FROM job_posts WHERE id = :id"), {"id": job_post_id}
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None
