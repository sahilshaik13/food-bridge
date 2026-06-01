"""
Invoke surplus pre-alert batch (same logic as POST /jobs/surplus-pre-alert).

Cloud Scheduler: GET/POST to Cloud Run URL with header X-FoodBridge-Job-Secret, or run this script
from a VM/cron with the same env as the API.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.services.demo_store import store  # noqa: E402
from app.services.surplus_prediction_service import run_surplus_pre_alert_job  # noqa: E402

if __name__ == "__main__":
    out = run_surplus_pre_alert_job(store)
    print(out)
