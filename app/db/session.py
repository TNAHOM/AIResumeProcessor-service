from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# Sync engine for existing code
engine = create_engine(settings.DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine for new async operations
async_engine = create_async_engine(
    settings.DB_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# Dependency to get a sync DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Async session context manager
async def get_async_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
