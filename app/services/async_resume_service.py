"""
Async version of resume service for S3 uploads and operations
"""
import uuid
from fastapi import UploadFile, HTTPException
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Try to import aioboto3
try:
    import aioboto3
    from botocore.exceptions import ClientError
    AIOBOTO3_AVAILABLE = True
except ImportError as e:
    logger.warning(f"aioboto3 not available: {e}")
    AIOBOTO3_AVAILABLE = False
    aioboto3 = None
    ClientError = Exception

async def upload_to_s3_async(file: UploadFile, s3_path: str):
    """Async S3 upload using aioboto3"""
    if not AIOBOTO3_AVAILABLE:
        raise RuntimeError("aioboto3 is required for async S3 operations")
        
    session = aioboto3.Session()
    
    try:
        async with session.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        ) as s3_client:
            # Reset file position to beginning 
            await file.seek(0) if hasattr(file, 'seek') else None
            
            # Read file content
            file_content = await file.read()
            
            # Upload to S3
            await s3_client.put_object(
                Bucket=settings.AWS_S3_BUCKET_NAME,
                Key=s3_path,
                Body=file_content
            )
            
            logger.info(f"✅ Uploaded {file.filename} -> s3://{settings.AWS_S3_BUCKET_NAME}/{s3_path}")
            
    except ClientError as e:
        logger.error(f"❌ S3 Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to S3.")
    except Exception as e:
        logger.error(f"❌ Unexpected error during S3 upload: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error during file upload.")