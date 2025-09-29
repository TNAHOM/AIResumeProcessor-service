from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Synchronous engine and session (existing)
engine = create_engine(settings.DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Asynchronous engine and session (new) - with optional import
try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    
    async_engine = create_async_engine(settings.ASYNC_DB_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    ASYNC_SUPPORT = True
except ImportError:
    # Async dependencies not installed
    async_engine = None
    AsyncSessionLocal = None
    ASYNC_SUPPORT = False
    print("⚠️  Async database support not available. Install: pip install asyncpg sqlalchemy[asyncio]")


# Dependency to get a synchronous DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Dependency to get an asynchronous DB session
async def get_async_db():
    if not ASYNC_SUPPORT:
        raise RuntimeError("Async database support not available")
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Function to get async session for workers
async def get_async_session():
    """Get async session for use in workers and async contexts."""
    if not ASYNC_SUPPORT:
        raise RuntimeError("Async database support not available")
    
    return AsyncSessionLocal()
