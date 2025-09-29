from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_URL: str
    ASYNC_DB_URL: str = ""
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_DEFAULT_REGION: str
    AWS_S3_BUCKET_NAME: str
    GEMINI_API_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"

    def __init__(self, **data):
        super().__init__(**data)
        # Auto-generate async DB URL if not provided
        if not self.ASYNC_DB_URL and self.DB_URL:
            self.ASYNC_DB_URL = self.DB_URL.replace("postgresql://", "postgresql+asyncpg://")


settings = Settings()  # pyright: ignore[reportCallIssue]
