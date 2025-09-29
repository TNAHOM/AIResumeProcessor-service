import json
import logging
import uuid
import asyncio
from typing import Optional

from sqlalchemy import select
from app.db.session import AsyncSessionLocal, SessionLocal
from app.db.models import Application, ApplicationStatus
from app.core.config import settings
from app.services.embeding_service import EmbeddingTaskType, TitleType, create_embedding_async
from app.services.job_post_service import get_job_post_by_id
from app.services.similarity_search import calculate_score, similarity_search
from app.services.textract_grouper import grouping
from app.services.gemini_service import (
    evaluate_resume_against_job_post_async,
    structure_and_normalize_resume_with_gemini_async,
)
from app.services.textract_service import AsyncTextractService

# Configure module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


async def process_resume_async(application_id: uuid.UUID, job_post_id: uuid.UUID):
    """
    Async version of resume processing pipeline
    """
    logger.info("Starting async resume processing for application %s", application_id)
    
    async with AsyncSessionLocal() as db:
        app = None
        try:
            # Step 1: Get the application from the database
            logger.info("Fetching application %s from DB", application_id)
            result = await db.execute(
                select(Application).where(Application.id == application_id)
            )
            app = result.scalar_one_or_none()
            
            if not app:
                logger.error("Application %s not found", application_id)
                raise ValueError(f"Application {application_id} not found")

            # Avoid reprocessing completed applications
            if app.status == ApplicationStatus.COMPLETED:
                logger.info(
                    "Application %s already completed; skipping processing", application_id
                )
                return

            # Update status to PROCESSING
            app.status = ApplicationStatus.PROCESSING
            await db.commit()
            logger.info("Application %s status updated to PROCESSING", application_id)

            # Step 1.5: Get job post information
            try:
                # Run synchronous job post fetch in executor since we don't have async version
                loop = asyncio.get_running_loop()
                with SessionLocal() as sync_db:
                    job_post = await loop.run_in_executor(
                        None, 
                        lambda: get_job_post_by_id(sync_db, job_post_id)
                    )
                    
                if (
                    not job_post
                    or not all(key in job_post for key in [
                        "description_embedding",
                        "requirements_embedding", 
                        "responsibilities_embedding"
                    ])
                ):
                    raise ValueError("Job post or its embeddings not found")

                job_description_embeded_value = job_post["description_embedding"]
                job_requirements = job_post["requirements_embedding"]
                responsibilities_embedding = job_post["responsibilities_embedding"]
                
            except Exception as e:
                logger.exception("Failed to fetch job post with id %s", job_post_id)
                app.failed_reason = f"Failed to fetch job post: {str(e)}"
                app.status = ApplicationStatus.FAILED
                await db.commit()
                raise

            # Step 2: Call Textract with async service
            if not app.s3_path:
                app.failed_reason = "S3 path is missing for this application"
                app.status = ApplicationStatus.FAILED
                await db.commit()
                logger.error("S3 path is None for application %s", application_id)
                raise ValueError("S3 path is missing for this application")

            textract_service = AsyncTextractService()
            try:
                job_id = await textract_service.start_job_async(
                    settings.AWS_S3_BUCKET_NAME, app.s3_path
                )
                logger.info(
                    "Textract job started: JobId=%s for s3_path=%s", job_id, app.s3_path
                )
            except Exception as e:
                logger.exception(
                    "Failed to start Textract job for application %s", application_id
                )
                app.failed_reason = f"Failed to start Textract job: {str(e)}"
                app.status = ApplicationStatus.FAILED
                await db.commit()
                raise

            raw_blocks = await textract_service.get_job_results_async(job_id)
            logger.info("Textract job succeeded. Got %d blocks.", len(raw_blocks))

            # Step 3: Group Textract results (run in executor since it's CPU-bound)
            try:
                loop = asyncio.get_running_loop()
                grouped_data = await loop.run_in_executor(None, lambda: grouping(raw_blocks))
            except Exception as e:
                logger.exception(
                    "Grouping of Textract results failed for application %s", application_id
                )
                app.failed_reason = f"Grouping failed: {str(e)}"
                app.status = ApplicationStatus.FAILED
                await db.commit()
                raise
            logger.info("Grouping complete.")

            # Step 4: Call the async Gemini service for final processing
            logger.info(
                "Sending to Gemini for normalization and extraction for application %s...",
                application_id,
            )
            final_data = await structure_and_normalize_resume_with_gemini_async(grouped_data)

            # Robust check for errors from the Gemini service
            if isinstance(final_data, dict) and final_data.get("error"):
                app.failed_reason = json.dumps(final_data)
                logger.error(
                    "Gemini processing failed: %s", final_data.get("details") or final_data
                )
                app.status = ApplicationStatus.FAILED
                await db.commit()
                raise RuntimeError(
                    f"Gemini Error: {final_data.get('details') or final_data}"
                )

            logger.info("Received final structured data from Gemini.")

            # Step 5: Embed the structured data
            logger.info("Creating embedding for application %s...", application_id)
            try:
                embeddingValue = await create_embedding_async(
                    json_contents=final_data,
                    task_type=EmbeddingTaskType.SEMANTIC_SIMILARITY,
                    title=TitleType.APPLICANT_RESUME,
                )
            except Exception as e:
                logger.exception(
                    "Embedding creation failed for application %s", application_id
                )
                app.failed_reason = f"Embedding creation failed: {str(e)}"
                app.status = ApplicationStatus.FAILED
                await db.commit()
                raise

            # Step 6: similarity search (run in executor since these are sync functions)
            logger.info(
                "Calculating similarity score for application %s...", application_id
            )
            try:
                loop = asyncio.get_running_loop()
                
                # Run similarity calculations in executor
                description_similarity = await loop.run_in_executor(
                    None,
                    lambda: similarity_search(
                        resumeData=embeddingValue, 
                        jobPostData=job_description_embeded_value
                    )
                )
                requirements_similarity = await loop.run_in_executor(
                    None,
                    lambda: similarity_search(
                        resumeData=embeddingValue, 
                        jobPostData=job_requirements
                    )
                )
                responsibilities_similarity = await loop.run_in_executor(
                    None,
                    lambda: similarity_search(
                        resumeData=embeddingValue, 
                        jobPostData=responsibilities_embedding
                    )
                )

                ai_analysis = await evaluate_resume_against_job_post_async(
                    resume_text=final_data, job_post=job_post
                )

                final_score = await loop.run_in_executor(
                    None,
                    lambda: calculate_score(
                        description=description_similarity,
                        requirement=requirements_similarity,
                        responsibility=responsibilities_similarity,
                        ai_score=ai_analysis.get("score", 1),
                        penality=0,
                    )
                )
                
            except Exception as e:
                logger.exception(
                    "similarity search failed for application %s", application_id
                )
                app.failed_reason = f"similarity search failed: {str(e)}"
                app.status = ApplicationStatus.FAILED
                await db.commit()
                raise

            # Final Step: Save the result to the database
            app.extracted_data = final_data
            app.embedded_value = embeddingValue
            app.analysis = ai_analysis
            app.status = ApplicationStatus.COMPLETED
            await db.commit()
            logger.info("Application %s fully completed and saved to DB.", application_id)

        except Exception as e:
            logger.exception(
                "An error occurred during async processing for application %s: %s",
                application_id,
                e,
            )
            try:
                if app and app.status != ApplicationStatus.COMPLETED:
                    app.status = ApplicationStatus.FAILED
                    # Append error details to failed_reason for debugging
                    reason = getattr(app, "failed_reason", None) or ""
                    try:
                        err_text = json.dumps({"error": str(e)})
                    except Exception:
                        err_text = str(e)
                    app.failed_reason = f"{reason}\n{err_text}" if reason else err_text
                    await db.commit()
            except Exception:
                logger.exception(
                    "Failed to mark application as FAILED in DB for %s", application_id
                )
            raise