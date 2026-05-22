from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Agricultural Operations Intelligence Platform",
)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.VERSION}
