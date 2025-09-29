"""
Async SQLAlchemy session setup with graceful fallback
"""
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import async SQLAlchemy components
try:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    ASYNC_SQLALCHEMY_AVAILABLE = True
    
    # Convert sync DB URL to async URL (change postgres:// to postgresql+asyncpg://)
    async_db_url = settings.DB_URL.replace("postgresql://", "postgresql+asyncpg://")
    
    try:
        # Create async engine
        async_engine = create_async_engine(async_db_url, echo=False)
        
        # Create async session factory
        AsyncSessionLocal = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        logger.info("Async SQLAlchemy initialized successfully")
        
    except Exception as e:
        logger.warning(f"Failed to initialize async SQLAlchemy: {e}")
        AsyncSessionLocal = None
        async_engine = None
        
except ImportError as e:
    logger.warning(f"Async SQLAlchemy components not available: {e}")
    ASYNC_SQLALCHEMY_AVAILABLE = False
    AsyncSessionLocal = None
    async_engine = None

# Dependency to get async DB session
async def get_async_db():
    """Get async database session with fallback handling"""
    if not ASYNC_SQLALCHEMY_AVAILABLE or not AsyncSessionLocal:
        raise RuntimeError("Async database session not available. Install asyncpg and ensure proper DB URL.")
        
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()