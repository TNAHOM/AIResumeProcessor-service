from fastapi import FastAPI
from app.db.session import engine
from app.db import models
from app.routers import resumes, health
from app.core.logging import setup_logging

# Setup logging
setup_logging()

# Create tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ATS Resume Parser Service",
    description="AI-powered resume processing service with Textract, Gemini, and embedding capabilities",
    version="1.0.0",
)

app.include_router(resumes.router)
app.include_router(health.router)


@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "ATS Resume Parser"}
