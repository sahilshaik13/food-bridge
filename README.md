# FoodBridge

Real-time AI-powered food surplus coordination for Hyderabad — connecting restaurants and hotels with verified NGOs, with compliance automation (FSSAI certificates, CSR reports), predictive intelligence, and Telegram-based donation flows.

| | |
|---|---|
| **Region** | `asia-south1` (Mumbai) |
| **Frontend** | [foodbridge-web](https://foodbridge-web-aqg35pktda-el.a.run.app) |
| **Backend API** | [foodbridge-api](https://foodbridge-api-aqg35pktda-el.a.run.app) |
| **API health** | [`GET /health`](https://foodbridge-api-aqg35pktda-el.a.run.app/health) · [`GET /health/ml`](https://foodbridge-api-aqg35pktda-el.a.run.app/health/ml) |
| **Telegram master bot** | [@food_bridgebot](https://t.me/food_bridgebot) |

---

## What it does

FoodBridge solves the coordination gap between food donors and NGOs: donors post surplus (web or Telegram), every posting is scanned by **Gemini Vision**, scored for accuracy and freshness, matched to nearby NGOs, and tracked through volunteer pickup to meals served. Municipal admins get heatmaps and compliance visibility; donors get FSSAI redistribution certificates and CSR impact PDFs.

**Product versions (roadmap):**

| Version | Focus |
|---------|--------|
| **V1** | Core coordination — post, scan, match, accept, volunteer pickup, RBAC dashboards |
| **V2** | Intelligence — freshness timers, escalation, emergency pledge pools, FSSAI/CSR PDFs, BigQuery logging |
| **V3** | Prediction & scale — surplus pre-alerts, heatmap, coverage gaps, leaderboard, multilingual Telegram |
| **V4** | Business layer — SaaS tiers, municipal white-label, NFSA automation (post-hackathon) |

Full requirements: [`FoodBridge_PRD.md`](FoodBridge_PRD.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Next.js 14 (app/ + frontend/src/)  ──fetch──►  FastAPI on Cloud Run    │
│  Firebase Auth (client)                          Firebase Admin (server)  │
│  Firebase RTDB listeners (live feeds)            Firestore (documents)    │
└─────────────────────────────────────────────────────────────────────────┘
         │                                              │
         │                                              ├── Vertex AI (Gemini) — scan, accuracy, matching, emergency
         │                                              ├── Cloud Storage — photos, PDFs
         │                                              ├── Cloud Tasks — escalation waves
         │                                              ├── Pub/Sub — optional async matching
         │                                              ├── BigQuery — ML training / analytics (optional)
         │                                              ├── Secret Manager — Telegram, OWM, etc.
         │                                              └── TeX Live (in API image) — FSSAI / CSR PDFs
         │
         └── Telegram: master bot (auth/setup) + per-donor slave bots (donations)
```

**Split GCP / Firebase projects (typical):**

- **Firebase project** — Auth, Firestore, Realtime Database, Storage (`FIREBASE_*` env vars).
- **GCP project** — Cloud Run, Vertex AI, Pub/Sub, Tasks, BigQuery, Secret Manager (`GOOGLE_CLOUD_PROJECT`).

See [`.env.example`](.env.example) and [`docs/cloud-configuration.md`](docs/cloud-configuration.md).

---

## Technology stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, Firebase Auth SDK |
| **Backend** | FastAPI, Python 3.11, Uvicorn |
| **AI** | Vertex AI — Gemini (`gemini-3-flash-preview`); heuristic + Vertex accuracy engine |
| **Primary DB** | Firestore (profiles, donations, sessions) |
| **Live feeds** | Firebase Realtime Database (active feeds, broadcasts, conversation state) |
| **Analytics** | BigQuery (+ optional BigQuery ML export) |
| **Events** | Cloud Pub/Sub (optional NGO matching pipeline) |
| **Jobs** | Cloud Tasks (escalation), Cloud Scheduler (surplus pre-alert) |
| **Storage** | Cloud Storage / Firebase Storage (photos, generated PDFs) |
| **Maps** | Google Maps Platform |
| **Bots** | Telegram Bot API — master + slave webhooks on Cloud Run |
| **Deploy** | Cloud Build → GCR → Cloud Run (`foodbridge-api`, `foodbridge-web`) |
| **Secrets** | Secret Manager (sync from env via script) |

---

## AI pipeline

Every donation passes through a multi-stage inference pipeline (not a single model call):

1. **Gemini Vision** — edibility scan, food type, freshness window, scan lineage (`model_id`, `model_version`, `fallback_used`).
2. **Accuracy engine** — Vertex JSON assessment with heuristic fallback, safety rails, optional OpenWeatherMap context and operational kitchen metrics.
3. **NGO matching** — proximity + nutrition + capacity; optional Gemini re-rank of heuristic queue.
4. **Escalation / emergency** — Cloud Tasks broadcast waves; emergency pool with Vertex-ranked donor pledge copy.
5. **Surplus prediction (V3)** — BigQuery ML + pre-alert job for NGOs.
6. **Closed loop** — pickup photos, meals served, donor trust score updates, optional ML export to BigQuery.

Details: [`foodbridge_ai_system.md`](foodbridge_ai_system.md) · [`backend/docs/phase3_accuracy_vertex.md`](backend/docs/phase3_accuracy_vertex.md)

---

## Roles & routes

| Role | Claim | Dashboard |
|------|-------|-----------|
| Super Admin | `super_admin` | `/admin`, `/admin/users` |
| Municipal Admin | `municipal_admin` | `/municipal` |
| Donor | `donor` | `/donor`, `/donor/donate`, `/donor/reports`, `/donor/history` |
| NGO Coordinator | `ngo_coordinator` | `/ngo`, `/ngo/emergency`, `/ngo/profile` |
| NGO Volunteer | `ngo_volunteer` | `/volunteer` |

Registration: `/onboarding/donor` (FSSAI auto-verify) · `/onboarding/ngo` (admin approval) · `/volunteer/register` (invite token).

Page tree and approval flows: [`FoodBridge_Hierarchy.md`](FoodBridge_Hierarchy.md)

API ↔ UI wiring: [`FoodBridge_Backend_Frontend_Spec.md`](FoodBridge_Backend_Frontend_Spec.md)

---

## Telegram (master + slave)

| Bot | Route | Purpose |
|-----|-------|---------|
| **Master** (`@food_bridgebot`) | `POST /telegram/master/webhook` | Link donor account, slave bot setup guide |
| **Slave** (one per restaurant) | `POST /telegram/slave/webhook` | `/donation`, `/track`, reports, status pushes |

Slave webhook base URL must match the Cloud Run API URL (`TELEGRAM_SLAVE_WEBHOOK_BASE_URL`). Slave bot tokens are stored encrypted (KMS / Secret Manager).

Full spec: [`FoodBridge_Telegram_Architecture.md`](FoodBridge_Telegram_Architecture.md)

---

## Repository layout

```
food-bridge/
├── app/                    # Next.js App Router pages
├── frontend/src/           # Shared components, lib (api.ts, AuthProvider, firebase)
├── backend/
│   ├── app/                # FastAPI application (routers, services, models)
│   ├── templates/          # LaTeX templates for FSSAI / CSR PDFs (Docker: FOODBRIDGE_TEMPLATE_ROOT)
│   └── Dockerfile          # API image — Python 3.11 + TeX Live + Vertex stack
├── Dockerfile              # Web image — Next.js multi-stage (build from repo root)
├── cloudbuild.yaml         # Build + deploy both Cloud Run services
├── scripts/                # Deploy, secrets sync, migrations, smoke checks
├── docs/                   # Implementation notes, cloud config
└── *.md                    # PRD, hierarchy, execution guide, AI spec, Telegram spec
```

Path alias: `@/*` → `./frontend/src/*` (see `tsconfig.json`).

---

## Local development

### Prerequisites

- Node.js 20+, pnpm (or npm)
- Python 3.11
- Google Cloud SDK (`gcloud`), Firebase CLI (optional)
- Service account JSON for Firebase Admin + GCP (local only — production uses ADC on Cloud Run)

### Setup

```bash
# Frontend (repo root)
cp .env.example .env.local
# Edit .env.local — Firebase web keys, credential paths, NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
pnpm install
pnpm dev          # http://localhost:3000

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# Uses repo-root .env.local via backend/app/core/config.py
uvicorn app.main:app --reload --port 8000
```

OpenAPI docs (local): http://127.0.0.1:8000/docs

Phase-by-phase build guide: [`FoodBridge_Execution.md`](FoodBridge_Execution.md)

---

## Docker

### Frontend (repo root)

Multi-stage build: deps → `pnpm run build` with **`NEXT_PUBLIC_*` build-args** → `next start` on port **8080**.

```bash
docker build -f Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://foodbridge-api-aqg35pktda-el.a.run.app \
  --build-arg NEXT_PUBLIC_FIREBASE_API_KEY=... \
  # ... other NEXT_PUBLIC_* from .env.production
  -t foodbridge-web .
```

See root [`Dockerfile`](Dockerfile) for the full build-arg list.

### Backend (repo root context)

Includes **TeX Live** for PDF generation and the full AI/Vertex code path.

```bash
docker build -f backend/Dockerfile -t foodbridge-api .
docker run -p 8080:8080 --env-file .env.local foodbridge-api
```

---

## Deploy to Cloud Run

**Recommended (Windows):** sync secrets from env, then Cloud Build with production substitutions:

```powershell
gcloud config set project YOUR_GCP_PROJECT
.\scripts\sync_env_to_gcp_secrets.ps1 -EnvFile .env.local -GrantIam
.\scripts\deploy_foodbridge_cloud_run.ps1 -EnvFile .env.production
```

**Manual:**

```bash
gcloud builds submit . --config cloudbuild.yaml --project YOUR_GCP_PROJECT
```

`cloudbuild.yaml` builds and deploys:

- **`foodbridge-api`** — 2 vCPU, 2 GiB; Vertex flags on; secrets for `OPENWEATHERMAP_API_KEY`, `TELEGRAM_*`
- **`foodbridge-web`** — Next.js; `NEXT_PUBLIC_*` baked at build time

After first deploy, align:

- `_NEXT_PUBLIC_API_BASE_URL` / `.env.production` → API Cloud Run URL
- `_FRONTEND_BASE_URL` / `CORS_ALLOW_ORIGINS` → web Cloud Run URL (or Firebase Hosting)
- `_TELEGRAM_SLAVE_WEBHOOK_BASE_URL` → API Cloud Run URL

Detailed runbook: [`backend/docs/deploy_cloud_run.md`](backend/docs/deploy_cloud_run.md)

**Public access:** grant `roles/run.invoker` to `allUsers` on both services if org policy allows:

```bash
gcloud run services add-iam-policy-binding foodbridge-web \
  --region=asia-south1 --member=allUsers --role=roles/run.invoker
gcloud run services add-iam-policy-binding foodbridge-api \
  --region=asia-south1 --member=allUsers --role=roles/run.invoker
```

---

## Environment variables

Copy [`.env.example`](.env.example) → `.env.local` (local) or `.env.production` (Cloud Build substitutions).

| Group | Examples |
|-------|----------|
| Firebase | `FIREBASE_PROJECT_ID`, `FIREBASE_DATABASE_URL`, `FIREBASE_ADMIN_CREDENTIALS` |
| GCP / Vertex | `GOOGLE_CLOUD_PROJECT`, `VERTEX_AI_*`, `ACCURACY_VERTEX_ENABLED`, `MATCHING_VERTEX_ENABLED` |
| Frontend (build-time) | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_FIREBASE_*`, `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` |
| Telegram | `TELEGRAM_MASTER_BOT_TOKEN`, `TELEGRAM_MASTER_SECRET`, `TELEGRAM_SLAVE_WEBHOOK_BASE_URL` |
| Optional | `OPENWEATHERMAP_API_KEY`, `CORS_ALLOW_ORIGINS`, `DISABLE_AI_INTEGRATION` |

Never commit `.env.local`, `.env.production`, or service account JSON.

---

## Security

- **Production:** Application Default Credentials on Cloud Run; no JSON keys in containers.
- **Secrets:** Secret Manager; sync via [`scripts/sync_env_to_gcp_secrets.ps1`](scripts/sync_env_to_gcp_secrets.ps1).
- **Telegram:** Master webhook `secret_token`; slave tokens encrypted (KMS keyring).
- **Auth:** Firebase ID tokens on protected routes; custom claims for RBAC.
- **CORS:** Default allowlist includes localhost and Cloud Run web hostnames; override with `CORS_ALLOW_ORIGINS`.

---

## Documentation index

| Document | Contents |
|----------|----------|
| [`FoodBridge_PRD.md`](FoodBridge_PRD.md) | Product requirements, goals V1–V4, stack, non-goals |
| [`FoodBridge_Hierarchy.md`](FoodBridge_Hierarchy.md) | Roles, page tree, registration & approval flows |
| [`FoodBridge_Backend_Frontend_Spec.md`](FoodBridge_Backend_Frontend_Spec.md) | API routes, Firestore/RTDB map, frontend connections |
| [`FoodBridge_Execution.md`](FoodBridge_Execution.md) | Day-by-day build order, GCP CLI setup |
| [`foodbridge_ai_system.md`](foodbridge_ai_system.md) | AI modules, FoodSafe scoring, matching, metrics |
| [`FoodBridge_Telegram_Architecture.md`](FoodBridge_Telegram_Architecture.md) | Master/slave bots, webhooks, conversation state |
| [`docs/FoodBridge_full_implementation_detail.md`](docs/FoodBridge_full_implementation_detail.md) | Session implementation summary (deploy, weather, scan lineage) |
| [`backend/docs/deploy_cloud_run.md`](backend/docs/deploy_cloud_run.md) | Cloud Run deploy, IAM, troubleshooting |

**Backend phase docs:** `backend/docs/phase2_scan_metadata_migration.md`, `phase3_accuracy_vertex.md`, `phase6_ml_pipeline.md`, `phase7_monitoring.md`, `phase8_release_readiness.md`

---

## Useful scripts

| Script | Purpose |
|--------|---------|
| `scripts/deploy_foodbridge_cloud_run.ps1` | Cloud Build deploy with env substitutions |
| `scripts/sync_env_to_gcp_secrets.ps1` | Push `.env` keys to Secret Manager |
| `scripts/migrate_donation_scans.py` | Backfill `donation_scans` collection |
| `scripts/smoke_release_check.py` | Release smoke checklist |
| `backend/scripts/generate_data.py` | Seed demo donors/NGOs |

---

## License

Private / hackathon project — see repository owners for usage terms.
