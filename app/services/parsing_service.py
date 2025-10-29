import time
import boto3
from botocore.exceptions import BotoCoreError, ClientError
import logging
from app.core.config import settings

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
