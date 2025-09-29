"""Security utilities for file validation and input sanitization."""
import mimetypes
from typing import List, Optional
from fastapi import UploadFile, HTTPException
from app.core.logging import get_logger

logger = get_logger(__name__)

# Allowed file types for resume uploads
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword", 
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

# Maximum file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


def validate_file_upload(file: UploadFile) -> None:
    """Validate uploaded file for security and format compliance.
    
    Args:
        file: The uploaded file to validate
        
    Raises:
        HTTPException: If file validation fails
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Check file size
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400, 
            detail=f"File size too large. Maximum allowed: {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Check MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )
    
    # Additional check using filename extension
    if file.filename:
        mime_type, _ = mimetypes.guess_type(file.filename)
        if mime_type and mime_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"MIME type mismatch for file {file.filename}: header={file.content_type}, guessed={mime_type}")
    
    logger.info(f"File validation passed for: {file.filename} (type: {file.content_type}, size: {file.size})")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and other security issues.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    import re
    import os
    
    if not filename:
        return "unknown_file"
    
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove or replace dangerous characters
    filename = re.sub(r'[^\w\-_.]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    
    return filename