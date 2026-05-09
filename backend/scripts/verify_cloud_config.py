"""Non-destructive checks for the FoodBridge split-project credential setup."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402


def _read_project_id(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)["project_id"]


def main() -> int:
    settings = get_settings()

    firebase_credential_project = _read_project_id(settings.firebase_admin_credentials)
    gcp_credential_project = _read_project_id(settings.google_application_credentials)

    checks = {
        "firebase_project_id": settings.firebase_project_id,
        "firebase_credential_project": firebase_credential_project,
        "google_cloud_project": settings.google_cloud_project,
        "gcp_credential_project": gcp_credential_project,
        "firebase_storage_bucket": settings.firebase_storage_bucket,
        "firebase_database_url": settings.firebase_database_url,
        "gcp_location": settings.gcp_location,
    }

    print(json.dumps(checks, indent=2))

    if firebase_credential_project != settings.firebase_project_id:
        print("Firebase credential project does not match FIREBASE_PROJECT_ID.", file=sys.stderr)
        return 1
    if gcp_credential_project != settings.google_cloud_project:
        print("GCP credential project does not match GOOGLE_CLOUD_PROJECT.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
