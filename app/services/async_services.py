"""
Async wrappers for external services (S3, Textract, embeddings).
This provides async interfaces for services that are traditionally synchronous.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import uuid
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.services.embeding_service import create_embedding, EmbeddingTaskType, TitleType

logger = logging.getLogger(__name__)


class AsyncS3Service:
    """Async S3 service wrapper."""
    
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        )
    
    async def upload_file_async(self, file_obj, bucket_name: str, s3_path: str) -> bool:
        """Upload file to S3 asynchronously."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                self.s3_client.upload_fileobj,
                file_obj,
                bucket_name,
                s3_path
            )
            logger.info(f"✅ Uploaded file -> s3://{bucket_name}/{s3_path}")
            return True
        except ClientError as e:
            logger.error(f"❌ S3 Upload failed: {e}")
            raise


class AsyncTextractService:
    """Async Textract service wrapper."""
    
    def __init__(self):
        self.client = boto3.client(
            "textract",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        )
    
    async def start_job_async(self, bucket_name: str, object_key: str) -> str:
        """Start Textract job asynchronously."""
        loop = asyncio.get_running_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.client.start_document_analysis(
                    DocumentLocation={
                        "S3Object": {"Bucket": bucket_name, "Name": object_key}
                    },
                    FeatureTypes=["LAYOUT", "FORMS"],
                )
            )
            
            job_id = response.get("JobId")
            if not job_id:
                logger.error(f"Textract start_document_analysis returned no JobId: {response}")
                raise RuntimeError("Textract did not return a job id")
            
            logger.info(f"Started Textract job: {job_id}")
            return job_id
        except (BotoCoreError, ClientError) as e:
            logger.exception("Error starting Textract job")
            raise
    
    async def get_job_results_async(self, job_id: str, max_wait_time: int = 300) -> List[Dict[str, Any]]:
        """Get Textract job results asynchronously with polling."""
        loop = asyncio.get_running_loop()
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            if asyncio.get_event_loop().time() - start_time > max_wait_time:
                raise TimeoutError(f"Textract job {job_id} timed out after {max_wait_time} seconds")
            
            try:
                response = await loop.run_in_executor(
                    None,
                    self.client.get_document_analysis,
                    {"JobId": job_id}
                )
                
                job_status = response.get("JobStatus")
                logger.info(f"Textract job {job_id} status: {job_status}")
                
                if job_status == "SUCCEEDED":
                    return await self._collect_all_pages_async(job_id)
                elif job_status == "FAILED":
                    status_message = response.get("StatusMessage", "Unknown error")
                    raise RuntimeError(f"Textract job failed: {status_message}")
                elif job_status in ["IN_PROGRESS"]:
                    # Wait before polling again
                    await asyncio.sleep(5)
                    continue
                else:
                    raise RuntimeError(f"Unexpected Textract job status: {job_status}")
                    
            except (BotoCoreError, ClientError) as e:
                logger.exception(f"Error checking Textract job {job_id}")
                raise
    
    async def _collect_all_pages_async(self, job_id: str) -> List[Dict[str, Any]]:
        """Collect all pages from Textract job results."""
        loop = asyncio.get_running_loop()
        blocks = []
        next_token = None
        
        while True:
            try:
                request = {"JobId": job_id}
                if next_token:
                    request["NextToken"] = next_token
                
                response = await loop.run_in_executor(
                    None,
                    self.client.get_document_analysis,
                    request
                )
                
                blocks.extend(response.get("Blocks", []))
                next_token = response.get("NextToken")
                
                if not next_token:
                    break
                    
            except (BotoCoreError, ClientError) as e:
                logger.exception(f"Error collecting Textract results for job {job_id}")
                raise
        
        logger.info(f"Collected {len(blocks)} blocks from Textract job {job_id}")
        return blocks


class AsyncEmbeddingService:
    """Async embedding service wrapper."""
    
    async def create_embedding_async(
        self,
        content: List[str],
        task_type: EmbeddingTaskType = EmbeddingTaskType.RETRIEVAL_DOCUMENT,
        title: Optional[str] = None,
        title_type: TitleType = TitleType.DOCUMENT
    ) -> List[float]:
        """Create embedding asynchronously."""
        loop = asyncio.get_running_loop()
        
        try:
            result = await loop.run_in_executor(
                None,
                create_embedding,
                content,
                task_type,
                title,
                title_type
            )
            logger.debug(f"Created embedding of dimension {len(result) if result else 0}")
            return result
        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")
            raise


# Global instances
async_s3_service = AsyncS3Service()
async_textract_service = AsyncTextractService()
async_embedding_service = AsyncEmbeddingService()