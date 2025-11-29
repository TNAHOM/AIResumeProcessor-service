from fastapi import FastAPI
from app.db.session import engine
from app.db import models
from app.routers import resumes

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="ATS Resume Parser Service")
app.include_router(resumes.router)


@app.get("/health", tags=["Health Check"])
def read_root():
    return {"status": "ok"}
