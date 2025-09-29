"""
Async resume processor - fully asynchronous pipeline for processing resumes.
Replaces the synchronous resume_processor.py with async/await patterns.
"""

import asyncio
import logging
import uuid
from typing import Optional

from app.db.session import get_async_session, ASYNC_SUPPORT
from app.db.models import Application, ApplicationStatus
from app.services.textract_grouper import grouping
from app.services.gemini_service import (
    evaluate_resume_against_job_post_async,
    structure_and_normalize_resume_with_gemini_async,
)
from app.services.job_post_service import get_job_post_by_id_async
from app.services.similarity_search import calculate_score, similarity_search
from app.core.config import settings

# Optional async service imports
try:
    from app.services.async_services import async_textract_service, async_embedding_service
    ASYNC_SERVICES_AVAILABLE = True
except ImportError:
    async_textract_service = None
    async_embedding_service = None
    ASYNC_SERVICES_AVAILABLE = False

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
    Async version of resume processing pipeline.
    
    Note: This is a demonstration of the async architecture. Some operations
    may fall back to sync if async dependencies are not available.
    """
    if not ASYNC_SUPPORT:
        logger.error("Async database support not available. Cannot process resume asynchronously.")
        return
    
    session = None
    
    try:
        # Step 1: Get database session and fetch application
        session = await get_async_session()
        
        # Fetch application with async query
        from sqlalchemy import select
        result = await session.execute(
            select(Application).where(Application.id == application_id)
        )
        app = result.scalar_one_or_none()
        
        if not app:
            logger.error(f"Application with ID {application_id} not found")
            return
        
        logger.info(f"Processing application {application_id} for job post {job_post_id}")
        
        # Update status to PROCESSING
        app.status = ApplicationStatus.PROCESSING
        await session.commit()
        
        # Step 2: Fetch job post data
        try:
            job_post = await get_job_post_by_id_async(job_post_id)
            if not job_post or not all(key in job_post for key in [
                "description_embedding", "requirements_embedding", "responsibilities_embedding"
            ]):
                raise ValueError("Job post or its embeddings not found")
            
            job_description_embedded_value = job_post["description_embedding"]
            job_requirements = job_post["requirements_embedding"]
            responsibilities_embedding = job_post["responsibilities_embedding"]
            
        except Exception as e:
            logger.exception(f"Failed to fetch job post with id {job_post_id}")
            app.failed_reason = f"Failed to fetch job post: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await session.commit()
            return
        
        # Step 3: Process with Textract (async if available, sync fallback)
        try:
            if not app.s3_path:
                raise ValueError("S3 path is missing for this application")
            
            if ASYNC_SERVICES_AVAILABLE and async_textract_service:
                # Use async Textract service
                job_id = await async_textract_service.start_job_async(
                    settings.AWS_S3_BUCKET_NAME, 
                    app.s3_path
                )
                logger.info(f"Textract job started: JobId={job_id} for s3_path={app.s3_path}")
                
                raw_blocks = await async_textract_service.get_job_results_async(job_id)
                logger.info(f"Textract job succeeded. Got {len(raw_blocks)} blocks.")
            else:
                # Fallback to sync Textract processing
                logger.warning("Using synchronous Textract processing (async services not available)")
                from app.workers.resume_processor import TextractService
                
                textract = TextractService()
                job_id = textract.start_job(settings.AWS_S3_BUCKET_NAME, app.s3_path)
                logger.info(f"Textract job started: JobId={job_id} for s3_path={app.s3_path}")
                
                # Poll for results in async-compatible way
                raw_blocks = await asyncio.get_event_loop().run_in_executor(
                    None, textract.get_job_results, job_id
                )
                logger.info(f"Textract job succeeded. Got {len(raw_blocks)} blocks.")
            
        except Exception as e:
            logger.exception(f"Failed Textract processing for application {application_id}")
            app.failed_reason = f"Failed Textract processing: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await session.commit()
            return
        
        # Step 4: Group Textract results
        try:
            grouped_text = grouping(raw_blocks)
            logger.info(f"Textract grouping succeeded. Got {len(grouped_text)} groups.")
        except Exception as e:
            logger.exception(f"Failed to group Textract results for application {application_id}")
            app.failed_reason = f"Failed to group Textract results: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await session.commit()
            return
        
        # Step 5: Normalize with Gemini AI
        try:
            normalized_data = await structure_and_normalize_resume_with_gemini_async(grouped_text)
            logger.info("Gemini normalization succeeded.")
            
            app.extracted_data = normalized_data
            await session.commit()
            
        except Exception as e:
            logger.exception(f"Failed Gemini normalization for application {application_id}")
            app.failed_reason = f"Failed Gemini normalization: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await session.commit()
            return
        
        # Step 6: Create embeddings
        try:
            # Prepare content for embedding (convert normalized data to text)
            embedding_content = []
            if normalized_data and isinstance(normalized_data, dict):
                for key, value in normalized_data.items():
                    if isinstance(value, (str, list)):
                        if isinstance(value, list):
                            embedding_content.extend([str(item) for item in value])
                        else:
                            embedding_content.append(str(value))
            
            if not embedding_content:
                embedding_content = ["No content available"]
            
            if ASYNC_SERVICES_AVAILABLE and async_embedding_service:
                embedded_value = await async_embedding_service.create_embedding_async(embedding_content)
            else:
                # Fallback to sync embedding creation
                from app.services.embeding_service import create_embedding, EmbeddingTaskType
                embedded_value = await asyncio.get_event_loop().run_in_executor(
                    None, create_embedding, embedding_content, EmbeddingTaskType.RETRIEVAL_DOCUMENT
                )
            
            logger.info(f"Embedding creation succeeded. Dimension: {len(embedded_value) if embedded_value else 0}")
            
            app.embedded_value = embedded_value
            await session.commit()
            
        except Exception as e:
            logger.exception(f"Failed embedding creation for application {application_id}")
            app.failed_reason = f"Failed embedding creation: {str(e)}"
            app.status = ApplicationStatus.FAILED
            await session.commit()
            return
        
        # Step 7: Calculate similarity and evaluation
        try:
            # Calculate similarity scores with job post embeddings
            if embedded_value and job_description_embedded_value:
                description_score = calculate_score(embedded_value, job_description_embedded_value)
                requirements_score = calculate_score(embedded_value, job_requirements)
                responsibilities_score = calculate_score(embedded_value, responsibilities_embedding)
                
                # Perform ATS evaluation
                evaluation_result = await evaluate_resume_against_job_post_async(
                    resume_text=grouped_text,
                    job_post=job_post
                )
                
                # Update analysis with scores and evaluation
                app.analysis = {
                    "similarity_scores": {
                        "description": description_score,
                        "requirements": requirements_score,
                        "responsibilities": responsibilities_score,
                    },
                    "evaluation": evaluation_result,
                    "overall_score": (description_score + requirements_score + responsibilities_score) / 3
                }
                
                logger.info(f"Similarity and evaluation completed. Overall score: {app.analysis['overall_score']:.2f}")
            
        except Exception as e:
            logger.exception(f"Failed similarity calculation for application {application_id}")
            # This is non-critical - we can still complete processing
            logger.warning("Continuing processing despite similarity calculation failure")
        
        # Step 8: Mark as completed
        app.status = ApplicationStatus.COMPLETED
        await session.commit()
        
        logger.info(f"✅ Successfully processed application {application_id}")
        
    except Exception as e:
        logger.exception(f"Unexpected error processing application {application_id}")
        
        if session:
            try:
                # Fetch fresh application state for error update
                from sqlalchemy import select
                result = await session.execute(
                    select(Application).where(Application.id == application_id)
                )
                app = result.scalar_one_or_none()
                
                if app:
                    reason = "Unexpected error during processing"
                    err_text = str(e)
                    app.failed_reason = f"{reason}\n{err_text}" if reason else err_text
                    app.status = ApplicationStatus.FAILED
                    await session.commit()
                    
            except Exception:
                logger.exception(f"Failed to mark application as FAILED in DB for {application_id}")
    
    finally:
        if session:
            await session.close()


async def start_async_worker():
    """Start the async worker to process jobs from the queue."""
    logger.info("Starting async resume processor worker...")
    
    if not ASYNC_SUPPORT:
        logger.error("Cannot start async worker: async database support not available")
        return
    
    # This would integrate with Redis queue in production
    # For now, this is a placeholder that can be called directly
    while True:
        try:
            # In production, this would poll Redis queue for jobs
            # For now, we'll sleep and wait for direct calls
            await asyncio.sleep(10)
            
        except KeyboardInterrupt:
            logger.info("Worker shutdown requested")
            break
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            await asyncio.sleep(5)  # Brief pause before retrying


if __name__ == "__main__":
    # For testing the async worker
    asyncio.run(start_async_worker())