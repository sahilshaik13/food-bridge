"""
Phase 6 — offline evaluation summaries from BigQuery donation_training_events.

Prints:
  - Terminal outcomes vs accuracy_recommendation (alignment counts).
  - Rows per accuracy_model_id (detector for drift).

Usage (repo root, .env.local with GOOGLE_CLOUD_PROJECT):
  python scripts/evaluate_ml_training_metrics.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def load_env() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line or line.startswith("export "):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_env()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("GOOGLE_CLOUD_PROJECT required", file=sys.stderr)
        sys.exit(1)

    from google.cloud import bigquery

    ds = os.environ.get("BIGQUERY_ML_DATASET", "foodbridge_ml")
    tbl = os.environ.get("BIGQUERY_ML_TABLE", "donation_training_events")
    fqtn = f"`{project}.{ds}.{tbl}`"

    client = bigquery.Client(project=project)

    q1 = f"""
    SELECT
      accuracy_recommendation,
      terminal_label,
      COUNT(*) AS n
    FROM {fqtn}
    WHERE event_type = 'terminal'
      AND accuracy_recommendation IS NOT NULL
    GROUP BY accuracy_recommendation, terminal_label
    ORDER BY n DESC
    """
    print("=== Terminal outcomes vs accuracy_recommendation ===")
    for row in client.query(q1).result():
        print(dict(row))

    q2 = f"""
    SELECT
      accuracy_model_id,
      accuracy_model_version,
      COUNT(*) AS n
    FROM {fqtn}
    WHERE event_type IN ('donation_created', 'backfill_snapshot')
    GROUP BY accuracy_model_id, accuracy_model_version
    ORDER BY n DESC
    """
    print("\n=== Rows per accuracy model (created / backfill) ===")
    for row in client.query(q2).result():
        print(dict(row))


if __name__ == "__main__":
    main()
