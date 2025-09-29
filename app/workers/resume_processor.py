import time
import boto3
import asyncio
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session
import json
import logging
from typing import Optional
import uuid

from app.db.session import SessionLocal
from app.db.models import Application, ApplicationStatus
from app.core.config import settings
from app.services.embeding_service import EmbeddingTaskType, TitleType
from app.services.job_post_service import get_job_post_by_id
from app.services.similarity_search import calculate_score, similarity_search
from app.services.textract_grouper import grouping
from app.services.gemini_service import (
    evaluate_resume_against_job_post,
    structure_and_normalize_resume_with_gemini,
    structure_and_normalize_resume_with_gemini_async,
    evaluate_resume_against_job_post_async,
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


class TextractService:
    def __init__(self):
        self.client = boto3.client(
            "textract",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        )

    def start_job(self, bucket_name: str, object_key: str):
        try:
            response = self.client.start_document_analysis(
                DocumentLocation={
                    "S3Object": {"Bucket": bucket_name, "Name": object_key}
                },
                FeatureTypes=["LAYOUT", "FORMS"],
            )
            job_id = response.get("JobId")
            if not job_id:
                logger.error(
                    "Textract start_document_analysis returned no JobId: %s", response
                )
                raise RuntimeError("Textract did not return a job id")
            return job_id
        except (BotoCoreError, ClientError):
            logger.exception("Error starting Textract job")
            raise

    async def start_job_async(self, bucket_name: str, object_key: str):
        """Async wrapper for start_job"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.start_job, bucket_name, object_key)

    def get_job_results(self, job_id):
        attempts = 0
        max_attempts = 120  # ~10 minutes polling (with 5s sleep)
        response = None
        while True:
            try:
                response = self.client.get_document_analysis(JobId=job_id)
            except (BotoCoreError, ClientError):
                attempts += 1
                logger.warning(
                    "Temporary error getting Textract job status (attempt %d)", attempts
                )
                if attempts >= 5:
                    logger.exception("Repeated failures querying Textract")
                    raise
                time.sleep(2)
                continue

            status = response.get("JobStatus")
            logger.info("Textract Job status: %s", status)
            if status == "SUCCEEDED":
                break
            elif status == "FAILED":
                msg = response.get("StatusMessage")
                logger.error("Textract job failed: %s", msg)
                raise RuntimeError(f"Textract job failed: {msg}")

            max_attempts -= 1
            if max_attempts <= 0:
                logger.error(
                    "Textract job polling exceeded timeout for JobId=%s", job_id
                )
                raise TimeoutError("Timed out waiting for Textract job to complete")
            time.sleep(5)

        results = []
        pages = [response]
        while response and response.get("NextToken"):
            try:
                time.sleep(0.2)
                response = self.client.get_document_analysis(
                    JobId=job_id, NextToken=response.get("NextToken")
                )
                pages.append(response)
            except (BotoCoreError, ClientError):
                logger.exception("Failed to fetch additional Textract pages")
                break

        for page in pages:
            blocks = page.get("Blocks") or []
            results.extend(blocks)
        return results

    async def get_job_results_async(self, job_id):
        """Async version of get_job_results with asyncio.sleep for polling"""
        attempts = 0
        max_attempts = 120  # ~10 minutes polling (with 5s sleep)
        response = None
        loop = asyncio.get_event_loop()
        
        while True:
            try:
                response = await loop.run_in_executor(
                    None, self.client.get_document_analysis, job_id
                )
            except (BotoCoreError, ClientError):
                attempts += 1
                logger.warning(
                    "Temporary error getting Textract job status (attempt %d)", attempts
                )
                if attempts >= 5:
                    logger.exception("Repeated failures querying Textract")
                    raise
                await asyncio.sleep(2)
                continue

            status = response.get("JobStatus")
            logger.info("Textract Job status: %s", status)
            if status == "SUCCEEDED":
                break
            elif status == "FAILED":
                msg = response.get("StatusMessage")
                logger.error("Textract job failed: %s", msg)
                raise RuntimeError(f"Textract job failed: {msg}")

            max_attempts -= 1
            if max_attempts <= 0:
                logger.error(
                    "Textract job polling exceeded timeout for JobId=%s", job_id
                )
                raise TimeoutError("Timed out waiting for Textract job to complete")
            await asyncio.sleep(5)

        results = []
        pages = [response]
        while response and response.get("NextToken"):
            try:
                await asyncio.sleep(0.2)
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.get_document_analysis(
                        JobId=job_id, NextToken=response.get("NextToken")
                    )
                )
                pages.append(response)
            except (BotoCoreError, ClientError):
                logger.exception("Failed to fetch additional Textract pages")
                break

        for page in pages:
            blocks = page.get("Blocks") or []
            results.extend(blocks)
        return results


async def process_resume_async(application_id: uuid.UUID, job_post_id: uuid.UUID):
    """Async version of process_resume for use with Celery and async workers"""
    logger.info("Starting async pipeline for application_id=%s", application_id)
    if not isinstance(application_id, uuid.UUID):
        logger.error("Invalid application_id provided: %s", application_id)
        return

    db: Optional[Session] = None
    app: Optional[Application] = None
    loop = asyncio.get_event_loop()
    
    try:
        # Run DB operations in executor since SQLAlchemy is sync
        db = await loop.run_in_executor(None, SessionLocal)
        app = await loop.run_in_executor(
            None, 
            lambda: db.query(Application).filter(Application.id == application_id).first()
        )
        
        if app is None:
            logger.warning("No application found with id %s", application_id)
            return

        # Avoid clobbering COMPLETED state if re-processing was attempted
        if app.status == ApplicationStatus.COMPLETED:
            logger.info(
                "Application %s already completed; skipping processing", application_id
            )
            return

        app.status = ApplicationStatus.PROCESSING
        await loop.run_in_executor(None, db.commit)

        # Step 1: Get the job Post embedded values
        logging.info("Fetching job post embedding for job_post_id %s...", job_post_id)
        try:
            job_post = await loop.run_in_executor(
                None, get_job_post_by_id, db, job_post_id
            )
            if (
                not job_post
                or (
                    "description_embedding",
                    "requirements_embedding",
                    "responsibilities_embedding",
                )
                not in job_post
            ):
                raise ValueError("Job post or its embeddings not found")

            job_description_embeded_value = job_post["description_embedding"]
            job_requirements = job_post["requirements_embedding"]
            responsibilities_embedding = job_post["responsibilities_embedding"]
        except Exception as e:
            logger.exception("Failed to fetch job post with id %s", job_post_id)
            app.failed_reason = f"Failed to fetch job post: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await loop.run_in_executor(None, db.commit)
            raise

        # Step 2: Call Textract with retries for transient failures
        textract = TextractService()
        try:
            if not app.s3_path:
                app.failed_reason = "S3 path is missing for this application"
                app.status = ApplicationStatus.FAILED
                await loop.run_in_executor(None, db.commit)
                logger.error("S3 path is None for application %s", application_id)
                raise ValueError("S3 path is missing for this application")

            job_id = await textract.start_job_async(settings.AWS_S3_BUCKET_NAME, app.s3_path)
            logger.info(
                "Textract job started: JobId=%s for s3_path=%s", job_id, app.s3_path
            )
        except Exception as e:
            logger.exception(
                "Failed to start Textract job for application %s", application_id
            )
            app.failed_reason = f"Failed to start Textract job: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await loop.run_in_executor(None, db.commit)
            raise

        raw_blocks = await textract.get_job_results_async(job_id)
        logger.info("Textract job succeeded. Got %d blocks.", len(raw_blocks))

        # Step 3: Group Textract results
        logger.info("Grouping Textract data for application %s...", application_id)
        try:
            grouped_data = await loop.run_in_executor(None, grouping, raw_blocks)
        except Exception as e:
            logger.exception(
                "Grouping of Textract results failed for application %s", application_id
            )
            app.failed_reason = f"Grouping failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await loop.run_in_executor(None, db.commit)
            raise
        logger.info("Grouping complete.")

        # Step 4: Call the advanced Gemini service for final processing
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
            await loop.run_in_executor(None, db.commit)
            raise RuntimeError(
                f"Gemini Error: {final_data.get('details') or final_data}"
            )

        logger.info("Received final structured data from Gemini.")

        # Step 5: Embed the structured data (run in executor as it may be blocking)
        logger.info("Creating embedding for application %s...", application_id)
        try:
            embeddingValue = await loop.run_in_executor(
                None,
                create_embedding,
                final_data,  # json_contents
                EmbeddingTaskType.SEMANTIC_SIMILARITY,
                TitleType.APPLICANT_RESUME,
            )
        except Exception as e:
            logger.exception(
                "Embedding creation failed for application %s", application_id
            )
            app.failed_reason = f"Embedding creation failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await loop.run_in_executor(None, db.commit)
            raise

        # Step 6: similarity search
        logger.info(
            "Calculating similarity score for application %s...", application_id
        )
        try:
            description_similarity = await loop.run_in_executor(
                None, similarity_search, embeddingValue, job_description_embeded_value
            )
            requirements_similarity = await loop.run_in_executor(
                None, similarity_search, embeddingValue, job_requirements
            )
            responsibilities_similarity = await loop.run_in_executor(
                None, similarity_search, embeddingValue, responsibilities_embedding
            )

            ai_analysis = await evaluate_resume_against_job_post_async(
                resume_text=final_data, job_post=job_post
            )

            await loop.run_in_executor(
                None,
                calculate_score,
                description_similarity,
                requirements_similarity,
                responsibilities_similarity,
                ai_analysis.get("score", 1),
                0,  # penalty
            )
        except Exception as e:
            logger.exception(
                "similarity search failed for application %s", application_id
            )
            app.failed_reason = f"similarity search failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await loop.run_in_executor(None, db.commit)
            raise

        # Final Step: Save the result to the database
        app.extracted_data = final_data
        app.embedded_value = embeddingValue
        app.analysis = ai_analysis
        app.status = ApplicationStatus.COMPLETED
        await loop.run_in_executor(None, db.commit)
        logger.info("Application %s fully completed and saved to DB.", application_id)

    except Exception as e:
        logger.exception(
            "An error occurred during processing for application %s: %s",
            application_id,
            e,
        )
        try:
            if db is None:
                db = await loop.run_in_executor(None, SessionLocal)
            if app is None:
                app = await loop.run_in_executor(
                    None,
                    lambda: db.query(Application)
                    .filter(Application.id == application_id)
                    .first()
                )
            if app and app.status != ApplicationStatus.COMPLETED:
                app.status = ApplicationStatus.FAILED
                # Append error details to failed_reason for debugging
                reason = getattr(app, "failed_reason", None) or ""
                try:
                    err_text = json.dumps({"error": str(e)})
                except Exception:
                    err_text = str(e)
                app.failed_reason = f"{reason}\n{err_text}" if reason else err_text
                await loop.run_in_executor(None, db.commit)
        except Exception:
            logger.exception(
                "Failed to mark application as FAILED in DB for %s", application_id
            )
    finally:
        if db:
            await loop.run_in_executor(None, db.close)


def process_resume(application_id: uuid.UUID, job_post_id: uuid.UUID):
    """Original synchronous version - kept for backwards compatibility"""
    logger.info("Starting full pipeline for application_id=%s", application_id)
    if not isinstance(application_id, uuid.UUID):
        logger.error("Invalid application_id provided: %s", application_id)
        return

    db: Optional[Session] = None
    app: Optional[Application] = None
    try:
        db = SessionLocal()
        app = db.query(Application).filter(Application.id == application_id).first()
        if app is None:
            logger.warning("No application found with id %s", application_id)
            return

        # Avoid clobbering COMPLETED state if re-processing was attempted
        if app.status == ApplicationStatus.COMPLETED:
            logger.info(
                "Application %s already completed; skipping processing", application_id
            )
            return

        app.status = ApplicationStatus.PROCESSING
        db.commit()

        # Step 1: Get the job Post embeded values
        logging.info("Fetching job post embedding for job_post_id %s...", job_post_id)
        try:
            job_post = get_job_post_by_id(db, job_post_id)
            if (
                not job_post
                or (
                    "description_embedding",
                    "requirements_embedding",
                    "responsibilities_embedding",
                )
                not in job_post
            ):
                raise ValueError("Job post or its embeddings not found")

            job_description_embeded_value = job_post["description_embedding"]
            job_requirements = job_post["requirements_embedding"]
            responsibilities_embedding = job_post["responsibilities_embedding"]
        except Exception as e:
            logger.exception("Failed to fetch job post with id %s", job_post_id)
            app.failed_reason = f"Failed to fetch job post: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise

        # Step 2: Call Textract with retries for transient failures
        textract = TextractService()
        try:
            if not app.s3_path:
                app.failed_reason = "S3 path is missing for this application"
                app.status = ApplicationStatus.FAILED
                db.commit()
                logger.error("S3 path is None for application %s", application_id)
                raise ValueError("S3 path is missing for this application")

            job_id = textract.start_job(settings.AWS_S3_BUCKET_NAME, app.s3_path)
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

        raw_blocks = textract.get_job_results(job_id)
        logger.info("Textract job succeeded. Got %d blocks.", len(raw_blocks))

        # Step 3: Group Textract results
        logger.info("Grouping Textract data for application %s...", application_id)
        try:
            grouped_data = grouping(raw_blocks)
        except Exception as e:
            logger.exception(
                "Grouping of Textract results failed for application %s", application_id
            )
            app.failed_reason = f"Grouping failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise
        logger.info("Grouping complete.")

        # Step 4: Call the advanced Gemini service for final processing
        logger.info(
            "Sending to Gemini for normalization and extraction for application %s...",
            application_id,
        )
        final_data = structure_and_normalize_resume_with_gemini(grouped_data)

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
            embeddingValue = create_embedding(
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
            db.commit()
            raise

        # Step 6: similarity search
        logger.info(
            "Calculating similarity score for application %s...", application_id
        )
        try:
            description_similarity = similarity_search(
                resumeData=embeddingValue, jobPostData=job_description_embeded_value
            )
            requirements_similarity = similarity_search(
                resumeData=embeddingValue, jobPostData=job_requirements
            )
            responsibilities_similarity = similarity_search(
                resumeData=embeddingValue, jobPostData=responsibilities_embedding
            )

            ai_analysis = evaluate_resume_against_job_post(
                resume_text=final_data, job_post=job_post
            )

            calculate_score(
                description=description_similarity,
                requirement=requirements_similarity,
                responsibility=responsibilities_similarity,
                ai_score=ai_analysis.get("score", 1),
                penality=0,
            )
        except Exception as e:
            logger.exception(
                "similarity search failed for application %s", application_id
            )
            app.failed_reason = f"similarity search failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            db.commit()
            raise

        # Final Step: Save the result to the database
        app.extracted_data = final_data
        app.embedded_value = embeddingValue
        app.analysis = ai_analysis
        app.status = ApplicationStatus.COMPLETED
        db.commit()
        logger.info("Application %s fully completed and saved to DB.", application_id)

    except Exception as e:
        logger.exception(
            "An error occurred during processing for application %s: %s",
            application_id,
            e,
        )
        try:
            if db is None:
                db = SessionLocal()
            if app is None:
                app = (
                    db.query(Application)
                    .filter(Application.id == application_id)
                    .first()
                )
            if app and app.status != ApplicationStatus.COMPLETED:
                app.status = ApplicationStatus.FAILED
                # Append error details to failed_reason for debugging
                reason = getattr(app, "failed_reason", None) or ""
                try:
                    err_text = json.dumps({"error": str(e)})
                except Exception:
                    err_text = str(e)
                app.failed_reason = f"{reason}\n{err_text}" if reason else err_text
                db.commit()
        except Exception:
            logger.exception(
                "Failed to mark application as FAILED in DB for %s", application_id
            )
    finally:
        if db:
            db.close()
