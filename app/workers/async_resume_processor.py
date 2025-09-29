"""
Async version of resume processor for improved throughput 
"""
import json
import logging
import uuid
from typing import Optional

try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    ASYNC_IMPORT_SUCCESS = True
except ImportError:
    AsyncSession = None
    select = None
    ASYNC_IMPORT_SUCCESS = False

from app.db.async_session import AsyncSessionLocal, ASYNC_SQLALCHEMY_AVAILABLE
from app.db.models import Application, ApplicationStatus

# Conditional imports for async services
try:
    from app.services.async_textract_service import AsyncTextractService
    ASYNC_TEXTRACT_AVAILABLE = True
except ImportError:
    AsyncTextractService = None
    ASYNC_TEXTRACT_AVAILABLE = False

from app.services.textract_grouper import grouping
from app.services.gemini_service import (
    structure_and_normalize_resume_with_gemini,
    evaluate_resume_against_job_post,
)
from app.services.embeding_service import create_embedding
from app.services.job_post_service import get_job_post_by_id
from app.services.similarity_search import calculate_score, similarity_search

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


async def process_resume_async(application_id: uuid.UUID, job_post_id: uuid.UUID):
    """Async version of process_resume for improved throughput"""
    logger.info("Starting async pipeline for application_id=%s", application_id)
    
    if not isinstance(application_id, uuid.UUID):
        logger.error("Invalid application_id provided: %s", application_id)
        return
    
    # Check if async dependencies are available
    if not ASYNC_SQLALCHEMY_AVAILABLE or not AsyncSessionLocal or not ASYNC_IMPORT_SUCCESS or not ASYNC_TEXTRACT_AVAILABLE:
        logger.warning("Async dependencies not available, falling back to sync processing")
        # Import and use sync processor as fallback
        from app.workers.resume_processor import process_resume
        return process_resume(application_id, job_post_id)
    
    db: Optional[AsyncSession] = None
    app: Optional[Application] = None
    
    try:
        # Step 1: Initialize async DB session and get application
        db = AsyncSessionLocal()
        
        # Query for application using async session
        result = await db.execute(select(Application).filter(Application.id == application_id))
        app = result.scalar_one_or_none()
        
        if app is None:
            logger.warning("No application found with id %s", application_id)
            return
        
        # Avoid re-processing completed applications
        if app.status == ApplicationStatus.COMPLETED:
            logger.info("Application %s already completed; skipping processing", application_id)
            return
        
        # Update status to PROCESSING
        app.status = ApplicationStatus.PROCESSING
        await db.commit()
        
        # Step 2: Fetch job post data (keeping this sync for now as it's complex to convert)
        logger.info("Fetching job post embedding for job_post_id %s...", job_post_id)
        try:
            # Note: get_job_post_by_id is still sync - would need async version
            # For now, we'll keep this sync call within the async function
            import asyncio
            from functools import partial
            from app.db.session import SessionLocal
            
            # Run sync job post query in executor
            sync_db = SessionLocal()
            try:
                job_post = await asyncio.get_event_loop().run_in_executor(
                    None, partial(get_job_post_by_id, sync_db, job_post_id)
                )
            finally:
                sync_db.close()
                
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
        
        # Step 3: Call Textract asynchronously
        textract = AsyncTextractService()
        try:
            if not app.s3_path:
                app.failed_reason = "S3 path is missing for this application"
                app.status = ApplicationStatus.FAILED
                await db.commit()
                logger.error("S3 path is None for application %s", application_id)
                raise ValueError("S3 path is missing for this application")
            
            # Start Textract job asynchronously
            from app.core.config import settings
            job_id = await textract.start_job(settings.AWS_S3_BUCKET_NAME, app.s3_path)
            logger.info("Textract job started: JobId=%s for s3_path=%s", job_id, app.s3_path)
            
            # Get results asynchronously with polling
            raw_blocks = await textract.get_job_results(job_id)
            logger.info("Textract job succeeded. Got %d blocks.", len(raw_blocks))
            
        except Exception as e:
            logger.exception("Failed to process Textract job for application %s", application_id)
            app.failed_reason = f"Textract processing failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await db.commit()
            raise
        
        # Step 4: Group Textract results (this is CPU-bound, run in executor)
        logger.info("Grouping Textract data for application %s...", application_id)
        try:
            grouped_data = await asyncio.get_event_loop().run_in_executor(
                None, grouping, raw_blocks
            )
        except Exception as e:
            logger.exception("Grouping of Textract results failed for application %s", application_id)
            app.failed_reason = f"Grouping failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await db.commit()
            raise
        logger.info("Grouping complete.")
        
        # Step 5: Call Gemini for normalization (already async in the service)
        logger.info("Sending to Gemini for normalization for application %s...", application_id)
        try:
            # Run Gemini calls in executor since they might be sync
            final_data = await asyncio.get_event_loop().run_in_executor(
                None, structure_and_normalize_resume_with_gemini, grouped_data
            )
            
            # Check for errors
            if isinstance(final_data, dict) and final_data.get("error"):
                app.failed_reason = json.dumps(final_data)
                logger.error("Gemini processing failed: %s", final_data.get("details") or final_data)
                app.status = ApplicationStatus.FAILED
                await db.commit()
                raise RuntimeError(f"Gemini processing failed: {final_data}")
                
        except Exception as e:
            logger.exception("Gemini normalization failed for application %s", application_id)
            app.failed_reason = f"Gemini normalization failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await db.commit()
            raise
        
        # Step 6: Create embeddings (run in executor)
        logger.info("Creating embeddings for application %s...", application_id)
        try:
            embeddingValue = await asyncio.get_event_loop().run_in_executor(
                None, create_embedding, final_data
            )
        except Exception as e:
            logger.exception("Embedding creation failed for application %s", application_id)
            app.failed_reason = f"Embedding creation failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await db.commit()
            raise
        
        # Step 7: Similarity search and AI analysis (run in executor)
        logger.info("Performing similarity analysis for application %s...", application_id)
        try:
            # Run similarity searches in executor
            description_similarity = await asyncio.get_event_loop().run_in_executor(
                None, similarity_search, embeddingValue, job_description_embeded_value
            )
            requirements_similarity = await asyncio.get_event_loop().run_in_executor(
                None, similarity_search, embeddingValue, job_requirements
            )
            responsibilities_similarity = await asyncio.get_event_loop().run_in_executor(
                None, similarity_search, embeddingValue, responsibilities_embedding
            )
            
            # AI analysis
            ai_analysis = await asyncio.get_event_loop().run_in_executor(
                None, evaluate_resume_against_job_post, final_data, job_post
            )
            
            # Calculate final score
            final_score = await asyncio.get_event_loop().run_in_executor(
                None,
                calculate_score,
                description_similarity,
                requirements_similarity, 
                responsibilities_similarity,
                ai_analysis.get("score", 1),
                0
            )
            
        except Exception as e:
            logger.exception("Similarity search failed for application %s", application_id)
            app.failed_reason = f"Similarity search failed: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await db.commit()
            raise
        
        # Step 8: Save final results to database
        app.extracted_data = final_data
        app.embedded_value = embeddingValue
        app.analysis = ai_analysis
        app.status = ApplicationStatus.COMPLETED
        await db.commit()
        
        logger.info("Application %s fully completed and saved to DB.", application_id)
        
    except Exception as e:
        logger.exception("An error occurred during async processing for application %s: %s", application_id, e)
        
        # Try to mark as failed
        try:
            if db is None:
                db = AsyncSessionLocal()
            if app is None:
                result = await db.execute(select(Application).filter(Application.id == application_id))
                app = result.scalar_one_or_none()
                
            if app and app.status != ApplicationStatus.COMPLETED:
                app.status = ApplicationStatus.FAILED
                reason = getattr(app, "failed_reason", None) or ""
                try:
                    err_text = json.dumps({"error": str(e)})
                except Exception:
                    err_text = str(e)
                app.failed_reason = f"{reason}\n{err_text}" if reason else err_text
                await db.commit()
                
        except Exception:
            logger.exception("Failed to mark application as FAILED in DB for %s", application_id)
            
    finally:
        if db:
            await db.close()