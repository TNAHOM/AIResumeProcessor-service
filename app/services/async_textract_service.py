"""
Async Textract service for document analysis
"""
import asyncio
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import async boto3
try:
    import aioboto3
    from botocore.exceptions import BotoCoreError, ClientError
    AIOBOTO3_AVAILABLE = True
except ImportError as e:
    logger.warning(f"aioboto3 not available: {e}")
    AIOBOTO3_AVAILABLE = False
    aioboto3 = None
    BotoCoreError = Exception
    ClientError = Exception

class AsyncTextractService:
    """Async version of TextractService"""
    
    def __init__(self):
        if not AIOBOTO3_AVAILABLE:
            raise ImportError("aioboto3 is required for AsyncTextractService")
        self.session = aioboto3.Session()
    
    async def start_job(self, bucket_name: str, object_key: str) -> str:
        """Start an async Textract document analysis job"""
        try:
            async with self.session.client(
                "textract",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_DEFAULT_REGION,
            ) as client:
                response = await client.start_document_analysis(
                    DocumentLocation={
                        "S3Object": {"Bucket": bucket_name, "Name": object_key}
                    },
                    FeatureTypes=["LAYOUT", "FORMS"],
                )
                
                job_id = response.get("JobId")
                if not job_id:
                    logger.error("Textract start_document_analysis returned no JobId: %s", response)
                    raise RuntimeError("Textract did not return a job id")
                
                return job_id
                
        except (BotoCoreError, ClientError):
            logger.exception("Error starting Textract job")
            raise
    
    async def get_job_results(self, job_id: str) -> list:
        """Poll for and retrieve Textract job results asynchronously"""
        attempts = 0
        max_attempts = 120  # ~10 minutes polling (with 5s sleep)
        
        async with self.session.client(
            "textract",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        ) as client:
            
            while True:
                try:
                    response = await client.get_document_analysis(JobId=job_id)
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
                    logger.error("Textract job polling exceeded timeout for JobId=%s", job_id)
                    raise TimeoutError("Timed out waiting for Textract job to complete")
                
                await asyncio.sleep(5)
            
            # Collect all pages of results
            results = []
            pages = [response]
            
            while response and response.get("NextToken"):
                try:
                    await asyncio.sleep(0.2)  # Rate limiting
                    response = await client.get_document_analysis(
                        JobId=job_id, NextToken=response.get("NextToken")
                    )
                    pages.append(response)
                except (BotoCoreError, ClientError):
                    logger.exception("Failed to fetch additional Textract pages")
                    break
            
            # Extract blocks from all pages
            for page in pages:
                blocks = page.get("Blocks") or []
                results.extend(blocks)
            
            return results