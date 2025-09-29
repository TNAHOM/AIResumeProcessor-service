import asyncio
import aioboto3
from botocore.exceptions import ClientError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class AsyncS3Service:
    def __init__(self):
        self.session = aioboto3.Session()
    
    async def upload_file_async(self, file_obj, s3_path: str) -> None:
        """
        Upload file to S3 asynchronously
        
        Args:
            file_obj: File object to upload
            s3_path: S3 key path for the file
        """
        try:
            async with self.session.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_DEFAULT_REGION,
            ) as s3_client:
                await s3_client.upload_fileobj(
                    file_obj, 
                    settings.AWS_S3_BUCKET_NAME, 
                    s3_path
                )
                logger.info(f"✅ Uploaded file -> s3://{settings.AWS_S3_BUCKET_NAME}/{s3_path}")
        except ClientError as e:
            logger.error(f"❌ S3 Upload failed: {e}")
            raise