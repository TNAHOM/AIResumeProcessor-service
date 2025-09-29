"""Health check endpoints for monitoring service and dependencies."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from typing import Dict, Any

from app.db.session import get_db
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/health", tags=["Health Checks"])


@router.get("/")
def basic_health_check() -> Dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "ATS Resume Parser"}


@router.get("/detailed")
def detailed_health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Detailed health check including all dependencies."""
    results = {
        "service": "healthy",
        "database": "unknown",
        "s3": "unknown", 
        "textract": "unknown",
        "gemini": "unknown",
        "timestamp": None,
    }
    
    # Check database connectivity
    try:
        db.execute(text("SELECT 1"))
        results["database"] = "healthy"
        logger.info("Database health check passed")
    except Exception as e:
        results["database"] = f"unhealthy: {str(e)}"
        logger.error(f"Database health check failed: {e}")
    
    # Check S3 connectivity
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        )
        s3_client.head_bucket(Bucket=settings.AWS_S3_BUCKET_NAME)
        results["s3"] = "healthy"
        logger.info("S3 health check passed")
    except (BotoCoreError, ClientError) as e:
        results["s3"] = f"unhealthy: {str(e)}"
        logger.error(f"S3 health check failed: {e}")
    except Exception as e:
        results["s3"] = f"configuration error: {str(e)}"
        logger.error(f"S3 configuration error: {e}")
    
    # Check Textract connectivity  
    try:
        textract_client = boto3.client(
            'textract',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        )
        # Just check if we can create a client and make a basic call
        textract_client.get_document_analysis(JobId="test-id-for-health-check")
        results["textract"] = "healthy"  # This will actually fail but proves API is accessible
    except ClientError as e:
        if e.response['Error']['Code'] in ['InvalidJobId', 'InvalidParameterException']:
            results["textract"] = "healthy"  # Expected error means API is accessible
            logger.info("Textract health check passed")
        else:
            results["textract"] = f"unhealthy: {str(e)}"
            logger.error(f"Textract health check failed: {e}")
    except Exception as e:
        results["textract"] = f"configuration error: {str(e)}"
        logger.error(f"Textract configuration error: {e}")
    
    # Check Gemini API key configuration
    try:
        if settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY) > 10:
            results["gemini"] = "configured"
            logger.info("Gemini API key is configured")
        else:
            results["gemini"] = "not configured"
            logger.warning("Gemini API key is not properly configured")
    except Exception as e:
        results["gemini"] = f"configuration error: {str(e)}"
        logger.error(f"Gemini configuration error: {e}")
    
    from datetime import datetime
    results["timestamp"] = datetime.utcnow().isoformat()
    
    # Determine overall health
    unhealthy_services = [k for k, v in results.items() 
                         if isinstance(v, str) and v.startswith("unhealthy")]
    
    if unhealthy_services:
        logger.warning(f"Unhealthy services detected: {unhealthy_services}")
        raise HTTPException(
            status_code=503, 
            detail={
                "status": "degraded",
                "unhealthy_services": unhealthy_services,
                "details": results
            }
        )
    
    return results


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)) -> Dict[str, str]:
    """Readiness check - indicates if service is ready to handle requests."""
    try:
        # Check if database is accessible
        db.execute(text("SELECT 1"))
        
        # Check if required environment variables are set
        required_vars = [
            settings.DB_URL,
            settings.AWS_ACCESS_KEY_ID, 
            settings.AWS_SECRET_ACCESS_KEY,
            settings.AWS_S3_BUCKET_NAME,
            settings.GEMINI_API_KEY,
        ]
        
        if not all(required_vars):
            raise ValueError("Required environment variables not set")
            
        return {"status": "ready"}
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "not ready", "reason": str(e)}
        )