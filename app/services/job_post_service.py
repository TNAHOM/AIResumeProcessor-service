import uuid
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any
import logging


logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def get_job_post_by_id(db: Session, job_post_id) -> Optional[Dict[str, Any]]:
    result = db.execute(
        text("SELECT * FROM job_posts WHERE id = :id"), {"id": job_post_id}
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


def increment_job_post_applicant_count(db: Session, job_post_id: uuid.UUID) -> bool:
    logger.info(f"Incrementing applicant count for job_post_id: {job_post_id}")
    try:
        result = db.execute(
            text(
                "UPDATE job_posts SET applicant_count = applicant_count + 1 WHERE id = :id"
            ),
            {"id": job_post_id},
        )
        db.commit()

        return getattr(result, "rowcount", 0) == 1

    except Exception as e:
        logger.error(
            f"Error incrementing applicant count for job_post_id {job_post_id}: {e}"
        )
        return False
