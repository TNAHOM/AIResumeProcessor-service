from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DB_URL: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_DEFAULT_REGION: str
    AWS_S3_BUCKET_NAME: str
    GEMINI_API_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"


settings = Settings()  # pyright: ignore[reportCallIssue]
