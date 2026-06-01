from contextlib import asynccontextmanager
import warnings
import os

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://foodbridge.web.app",
    # Cloud Run service name is foodbridge-web (both regional + *.run.app hostnames).
    "https://foodbridge-web-285920197648.asia-south1.run.app",
    "https://foodbridge-web-aqg35pktda-el.a.run.app",
    # Legacy image names from earlier deploys.
    "https://foodbridge-frontend-285920197648.asia-south1.run.app",
    "https://foodbridge-frontend-aqg35pktda-el.a.run.app",
]


def _cors_allow_origins() -> list[str]:
    extra = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if not extra:
        return list(_DEFAULT_CORS_ORIGINS)
    merged = list(_DEFAULT_CORS_ORIGINS)
    for origin in extra.split(","):
        o = origin.strip()
        if o and o not in merged:
            merged.append(o)
    return merged

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
    description=(
        "Real-time AI-powered food surplus coordination backend connecting restaurants with verified NGOs.\n\n"
        "**Phase 2 — donation AI metadata:** `Donation.scan` includes optional `model_id`, `model_version`, "
        "`generated_at`, `fallback_used`. Optional `accuracy` carries explainability fields. "
        "`scan_contract_version` is **1** (legacy/partial lineage) or **2** when both `scan.model_id` and "
        "`scan.model_version` are set. See `backend/docs/phase2_scan_metadata_migration.md`.\n\n"
        "**Phase 3 — accuracy:** Vertex structured JSON assessment with heuristic fallback and safety rails; "
        "see `backend/docs/phase3_accuracy_vertex.md`.\n\n"
        "**Phase 6 — ML pipeline:** Optional BigQuery append-only training events; "
        "see `backend/docs/phase6_ml_pipeline.md`.\n\n"
        "**Phase 7 — observability:** `GET /health/ml` in-process counters + export failures to Firestore logs; "
        "see `backend/docs/phase7_monitoring.md`.\n\n"
        "**Phase 8 — release:** Smoke checklist and script; see `backend/docs/phase8_release_readiness.md`."
    ),
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "donations",
            "description": (
                "Surplus postings and lifecycle updates. Responses use `Donation`, including "
                "`scan` (GeminiScan), optional `accuracy` (AccuracyAssessment), and `scan_contract_version`."
            ),
        },
    ],
)

# Any Cloud Run hostname for this service (regional + *.a.run.app) — gcloud shows both shapes.
_RUN_APP_FOODBRIDGE_WEB = r"^https://foodbridge-(web|frontend)[^/]*\.run\.app$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=_RUN_APP_FOODBRIDGE_WEB,
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


@app.get("/health/ml")
def health_ml() -> dict:
    """Phase 7: lightweight ML / pipeline status for uptime monitors (no auth)."""
    from app.services.ml_training_export_service import get_ml_export_metrics
    from app.services.accuracy_engine import get_accuracy_pipeline_metrics

    settings = get_settings()
    return {
        "ok": True,
        "ml_export_bigquery_enabled": settings.ml_export_bigquery_enabled,
        "v3_prediction_bigquery_enabled": settings.v3_prediction_bigquery_enabled,
        "surplus_pre_alert_enabled": settings.surplus_pre_alert_enabled,
        "accuracy_vertex_enabled": settings.accuracy_vertex_enabled,
        "vertex_ai_model_id": settings.vertex_ai_model_id,
        "vertex_ai_model_version": settings.vertex_ai_model_version,
        "bigquery_ml_dataset": settings.bigquery_ml_dataset,
        "bigquery_ml_table": settings.bigquery_ml_table,
        "bigquery_export": get_ml_export_metrics(),
        "accuracy_pipeline": get_accuracy_pipeline_metrics(),
    }
