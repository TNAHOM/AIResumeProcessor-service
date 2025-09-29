import asyncio
import time
import logging
import aioboto3
from botocore.exceptions import BotoCoreError, ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)


class AsyncTextractService:
    def __init__(self):
        self.session = aioboto3.Session()

    async def start_job_async(self, bucket_name: str, object_key: str) -> str:
        """
        Start Textract document analysis job asynchronously
        
        Args:
            bucket_name: S3 bucket name
            object_key: S3 object key
            
        Returns:
            Job ID string
        """
        try:
            async with self.session.client(
                "textract",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_DEFAULT_REGION,
            ) as textract_client:
                response = await textract_client.start_document_analysis(
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

    async def get_job_results_async(self, job_id: str) -> list:
        """
        Get Textract job results with polling, asynchronously
        
        Args:
            job_id: Textract job ID
            
        Returns:
            List of blocks from all pages
        """
        async with self.session.client(
            "textract",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        ) as textract_client:
            
            # Poll for job completion
            timeout = 300  # 5 minutes
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    response = await textract_client.get_document_analysis(JobId=job_id)
                    job_status = response.get("JobStatus")
                    
                    if job_status == "SUCCEEDED":
                        logger.info("Textract job %s succeeded", job_id)
                        break
                    elif job_status == "FAILED":
                        logger.error("Textract job %s failed", job_id)
                        raise RuntimeError(f"Textract job {job_id} failed")
                    elif job_status in ["IN_PROGRESS"]:
                        logger.info("Textract job %s still in progress, waiting...", job_id)
                        await asyncio.sleep(5)
                    else:
                        logger.warning("Unknown Textract job status: %s", job_status)
                        await asyncio.sleep(5)
                        
                except (BotoCoreError, ClientError):
                    logger.exception("Failed to check Textract job status")
                    await asyncio.sleep(5)
            else:
                logger.error("Textract job polling exceeded timeout for JobId=%s", job_id)
                raise TimeoutError("Timed out waiting for Textract job to complete")

            # Collect all pages
            results = []
            pages = [response]
            
            while response and response.get("NextToken"):
                try:
                    await asyncio.sleep(0.2)
                    response = await textract_client.get_document_analysis(
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