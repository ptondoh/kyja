from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers.auth import router as auth_router
from app.routers.bookings import router as bookings_router
from app.routers.hairdressers import router as hairdressers_router
from app.routers.products import router as products_router
from app.routers.services import router as services_router

logger = structlog.get_logger()

app = FastAPI(
    title="KYJA BEAUTÉ API",
    version="0.1.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(services_router, prefix="/services", tags=["services"])
app.include_router(products_router, prefix="/products", tags=["products"])
app.include_router(bookings_router, prefix="/bookings", tags=["bookings"])
app.include_router(hairdressers_router, prefix="/hairdressers", tags=["hairdressers"])

storage_dir = Path(settings.LOCAL_STORAGE_DIR)
storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=storage_dir), name="media")


@app.get("/health")
def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
