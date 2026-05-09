from contextlib import asynccontextmanager
import warnings
import os

# Suppress Google Cloud SDK Python 3.10 deprecation warnings for cleaner local logs
warnings.filterwarnings("ignore", category=FutureWarning, module="google.api_core.*")
warnings.filterwarnings("ignore", category=FutureWarning, module="google.cloud.*")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import admin, auth, communications, donations, entities, intelligence, reports, telegram, escalation


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"FoodBridge API starting")
    print(f"  Firebase project: {settings.firebase_project_id}")
    print(f"  GCP project: {settings.google_cloud_project}")
    print(f"  Firestore sync: {settings.firestore_sync_enabled}")
    print(f"  Region: {settings.gcp_location}")
    yield
    print("FoodBridge API shutting down")


app = FastAPI(
    title="FoodBridge API",
    version="1.0.0",
    description="Real-time AI-powered food surplus coordination backend connecting restaurants with verified NGOs.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://foodbridge.web.app",
        "https://foodbridge-frontend-285920197648.asia-south1.run.app",
        "https://foodbridge-frontend-aqg35pktda-el.a.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    if request.method == "GET":
        # Cache for 60 seconds on CDN
        response.headers["Cache-Control"] = "public, max-age=60, s-maxage=60"
    return response

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(communications.router)
app.include_router(donations.router)
app.include_router(entities.router)
app.include_router(escalation.router)
app.include_router(intelligence.router)
app.include_router(reports.router)
app.include_router(telegram.router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "service": "foodbridge-api",
        "version": "1.0.0",
        "firebase_project": settings.firebase_project_id,
        "gcp_project": settings.google_cloud_project,
    }
