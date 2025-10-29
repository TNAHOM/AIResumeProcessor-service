from sqlalchemy.orm import Session
import json
import logging
from typing import Optional
import uuid

from app.db.session import SessionLocal
from app.db.models import Application, ApplicationStatus
from app.core.config import settings
from app.services.embeding_service import EmbeddingTaskType, TitleType
from app.services.job_post_service import get_job_post_by_id, increment_job_post_applicant_count
from app.services.parsing_service import TextractService
from app.services.similarity_search import calculate_score, similarity_search
from app.services.textract_grouper import grouping
from app.services.gemini_service import (
    evaluate_resume_against_job_post,
    structure_and_normalize_resume_with_gemini,
)
from app.services.embeding_service import create_embedding

# Configure module logger. In production the application should configure handlers/formatters
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _fetch_application(db: Session, application_id: uuid.UUID) -> Optional[Application]:
    app = db.query(Application).filter(Application.id == application_id).first()
    if app is None:
        logger.warning("No application found with id %s", application_id)
        return None

    if app.status == ApplicationStatus.COMPLETED:
        logger.info(
            "Application %s already completed; skipping processing", application_id
        )
        return None

    return app


def _fetch_job_post_embeddings(db: Session, job_post_id: uuid.UUID):
    job_post = get_job_post_by_id(db, job_post_id)

    if not job_post or not all(
        key in job_post
        for key in (
            "description_embedding",
            "requirements_embedding",
            "responsibilities_embedding",
        )
    ):
        raise ValueError("Job post or its embeddings not found")

    return (
        job_post,
        job_post["description_embedding"],
        job_post["requirements_embedding"],
        job_post["responsibilities_embedding"],
    )


def _start_textract_job(textract: TextractService, app: Application) -> str:
    if not app.s3_path:
        logger.error("S3 path is None for application %s", app.id)
        raise ValueError("S3 path is missing for this application")

    return textract.start_job(settings.AWS_S3_BUCKET_NAME, app.s3_path)


def _get_textract_blocks(textract: TextractService, job_id: str):
    raw_blocks = textract.get_job_results(job_id)
    logger.info("Textract job succeeded. Got %d blocks.", len(raw_blocks))
    return raw_blocks


def _group_textract_results(raw_blocks, application_id: uuid.UUID):
    logger.info("Grouping Textract data for application %s...", application_id)
    grouped_data = grouping(raw_blocks)
    logger.info("Grouping complete.")
    return grouped_data


def _normalize_resume(grouped_data):
    return structure_and_normalize_resume_with_gemini(grouped_data)


def _create_resume_embedding(final_data):
    return create_embedding(
        json_contents=final_data,
        task_type=EmbeddingTaskType.RETRIEVAL_DOCUMENT,
        title=TitleType.APPLICANT_RESUME,
    )


def _compute_similarities(
    embedding_value,
    final_data,
    job_post,
    job_description_embedding,
    job_requirements,
    responsibilities_embedding,
):
    if isinstance(job_description_embedding, str):
        job_description_embedding = json.loads(job_description_embedding)
    if isinstance(job_requirements, str):
        job_requirements = json.loads(job_requirements)
    if isinstance(responsibilities_embedding, str):
        responsibilities_embedding = json.loads(responsibilities_embedding)

    description_similarity = similarity_search(
        resumeData=embedding_value, jobPostData=job_description_embedding
    )
    requirements_similarity = similarity_search(
        resumeData=embedding_value, jobPostData=job_requirements
    )
    responsibilities_similarity = similarity_search(
        resumeData=embedding_value, jobPostData=responsibilities_embedding
    )

    ai_analysis = evaluate_resume_against_job_post(
        resume_text=final_data,
        job_post=job_post,
    )

    if not isinstance(ai_analysis, dict):
        raise ValueError("AI analysis result must be a dictionary")

    calculate_score(
        description=description_similarity,
        requirement=requirements_similarity,
        responsibility=responsibilities_similarity,
        ai_score=ai_analysis.get("score", 1),
        penality=0,
    )

    return ai_analysis


def _finalize_success(
    db: Session,
    app: Application,
    final_data,
    embedding_value,
    ai_analysis,
):
    app.extracted_data = final_data
    app.embedded_value = embedding_value
    app.analysis = ai_analysis
    app.status = ApplicationStatus.COMPLETED
    db.commit()


def _finalize_failure(
    db: Optional[Session],
    app: Optional[Application],
    application_id: uuid.UUID,
    error: Exception,
):
    try:
        if db is None:
            db = SessionLocal()

        if app is None:
            app = db.query(Application).filter(Application.id == application_id).first()

        if app and app.status != ApplicationStatus.COMPLETED:
            app.status = ApplicationStatus.FAILED
            reason = getattr(app, "failed_reason", None) or ""
            try:
                err_text = json.dumps({"error": str(error)})
            except Exception:
                err_text = str(error)
            app.failed_reason = f"{reason}\n{err_text}" if reason else err_text
            db.commit()
    except Exception:
        logger.exception(
            "Failed to mark application as FAILED in DB for %s", application_id
        )

    return db, app


def process_resume(application_id: uuid.UUID, job_post_id: uuid.UUID):
    logger.info("Starting full pipeline for application_id=%s", application_id)
    if not isinstance(application_id, uuid.UUID):
        logger.error("Invalid application_id provided: %s", application_id)
        return

    db: Optional[Session] = None
    app: Optional[Application] = None
    try:
        db = SessionLocal()
        app = _fetch_application(db, application_id)
        if app is None:
            return

        app.status = ApplicationStatus.PROCESSING
        db.commit()

        # Step 1: Get the job Post embeded values
        logging.info("Fetching job post embedding for job_post_id %s...", job_post_id)
        try:
            (
                job_post,
                job_description_embeded_value,
                job_requirements,
                responsibilities_embedding,
            ) = _fetch_job_post_embeddings(db, job_post_id)
        except Exception as e:
            logger.exception("Failed to fetch job post with id %s", job_post_id)
            app.failed_reason = f"Failed to fetch job post: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise

        # Step 2: Call Textract with retries for transient failures
        try:
            textract = TextractService()
            job_id = _start_textract_job(textract, app)
            logger.info(
                "Textract job started: JobId=%s for s3_path=%s", job_id, app.s3_path
            )
        except Exception as e:
            logger.exception(
                "Failed to start Textract job for application %s", application_id
            )
            app.failed_reason = f"Failed to start Textract job: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise

        raw_blocks = _get_textract_blocks(textract, job_id)

        # Step 3: Group Textract results
        try:
            grouped_data = _group_textract_results(raw_blocks, application_id)
        except Exception as e:
            logger.exception(
                "Grouping of Textract results failed for application %s", application_id
            )
            app.failed_reason = f"Grouping failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise

        # Step 4: Call the advanced Gemini service for final processing
        logger.info(
            "Sending to Gemini for normalization and extraction for application %s...",
            application_id,
        )
        final_data = _normalize_resume(grouped_data)

        # Robust check for errors from the Gemini service
        if isinstance(final_data, dict) and final_data.get("error"):
            app.failed_reason = json.dumps(final_data)
            logger.error(
                "Gemini processing failed: %s", final_data.get("details") or final_data
            )
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise RuntimeError(
                f"Gemini Error: {final_data.get('details') or final_data}"
            )

        logger.info("Received final structured data from Gemini.")

        # Step 5: Embed the structured data
        logger.info("Creating embedding for application %s...", application_id)
        try:
            embeddingValue = _create_resume_embedding(final_data)
        except Exception as e:
            logger.exception(
                "Embedding creation failed for application %s", application_id
            )
            app.failed_reason = f"Embedding creation failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise

        # Step 6: similarity search
        logger.info(
            "Calculating similarity score for application %s...", application_id
        )
        try:
            ai_analysis = _compute_similarities(
                embedding_value=embeddingValue,
                final_data=final_data,
                job_post=job_post,
                job_description_embedding=job_description_embeded_value,
                job_requirements=job_requirements,
                responsibilities_embedding=responsibilities_embedding,
            )
        except Exception as e:
            logger.exception(
                "similarity search failed for application %s", application_id
            )
            app.failed_reason = f"similarity search failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise

        # Step 7: add number of applicant in the field of job post
        increment_job_post_applicant_count(db, job_post_id)
    
        # Final Step: Save the result to the database
        _finalize_success(db, app, final_data, embeddingValue, ai_analysis)
        logger.info("Application %s fully completed and saved to DB.", application_id)

    except Exception as e:
        logger.exception(
            "An error occurred during processing for application %s: %s",
            application_id,
            e,
        )
        db, app = _finalize_failure(db, app, application_id, e)
    finally:
        if db:
            db.close()
