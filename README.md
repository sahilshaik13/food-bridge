# FoodBridge

Secure, real-time food donation platform for Hyderabad.

## Production URLs

- **Frontend:** [https://foodbridge-frontend-285920197648.asia-south1.run.app](https://foodbridge-frontend-285920197648.asia-south1.run.app)
- **Backend API:** [https://foodbridge-api-285920197648.asia-south1.run.app](https://foodbridge-api-285920197648.asia-south1.run.app)
- **Telegram Master Bot:** [@FoodBridgeBot](https://t.me/FoodBridgeBot)

## Technology Stack

- **Frontend:** Next.js 14, TypeScript, Tailwind CSS, Firebase Auth
- **Backend:** FastAPI, Python 3.11, Vertex AI (Gemini 1.5 Flash)
- **Database:** Firestore (Metadata/Sessions), Firebase Realtime DB (Live Map/Conversations)
- **Infrastructure:** Google Cloud Run (8-CPU, 4GB RAM), Cloud KMS (Secret Management)

## Security Hardening

- **Application Default Credentials (ADC):** No local JSON keys used in production.
- **Cloud KMS:** Sensitive Telegram bot tokens are encrypted at rest.
- **Webhook Secrets:** Master bot webhook is protected by a 32-byte hex secret.
- **Environment Isolation:** Secrets managed via Cloud Run environment variables.

## Deployment Instructions

### Backend
```bash
cd backend
gcloud run deploy foodbridge-api --source . --region asia-south1 --cpu 8 --memory 4Gi
```

### Frontend
```bash
gcloud run deploy foodbridge-frontend --source . --region asia-south1 --cpu 8 --memory 4Gi
```

## Telegram Webhook Setup
The master bot webhook is configured to:
`https://foodbridge-api-285920197648.asia-south1.run.app/telegram/master/webhook`
