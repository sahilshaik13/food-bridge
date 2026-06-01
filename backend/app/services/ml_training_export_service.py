"""
Phase 6: append-only BigQuery training / evaluation events for donations.
Never raises to callers — failures are logged so donation flows stay healthy.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from app.core.cloud_clients import get_bigquery_client
from app.core.config import get_settings
from app.models import Donation

_TABLE_LOCK = threading.Lock()
_TABLE_READY = False

_METRICS_LOCK = threading.Lock()
_ml_export_attempted = 0
_ml_export_succeeded = 0
_ml_export_failed = 0
_ml_last_error: str | None = None
_ml_last_success_at: datetime | None = None
_ml_last_failure_at: datetime | None = None

_TERMINAL_STATUSES = frozenset({"completed", "wasted", "expired", "declined"})


def _iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    s = dt.isoformat()
    if s.endswith("+00:00"):
        return s.replace("+00:00", "Z")
    return s


def donation_event_to_row(
    donation: Donation,
    event_type: str,
    *,
    previous_status: str | None = None,
    terminal_label: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    acc = donation.accuracy
    scan = donation.scan
    row: dict[str, Any] = {
        "ingested_at": _iso_utc(now),
        "event_type": event_type,
        "donation_id": donation.id,
        "donor_id": donation.donor_id,
        "donation_status": donation.status.value,
        "previous_status": previous_status,
        "food_type": donation.food_type,
        "quantity_kg": float(donation.quantity_kg),
        "meal_count": int(donation.meal_count),
        "scan_passed": bool(scan.passed),
        "scan_confidence": float(scan.confidence),
        "scan_fallback_used": bool(scan.fallback_used),
        "scan_model_id": scan.model_id,
        "scan_model_version": scan.model_version,
        "accuracy_score": float(acc.score) if acc else None,
        "accuracy_band": acc.band if acc else None,
        "accuracy_recommendation": acc.recommendation if acc else None,
        "accuracy_fallback_used": bool(acc.fallback_used) if acc else None,
        "accuracy_model_id": acc.model_id if acc else None,
        "accuracy_model_version": acc.model_version if acc else None,
        "scan_contract_version": int(getattr(donation, "scan_contract_version", 1)),
        "terminal_label": terminal_label,
        "meals_served": int(donation.completed_meals_served) if donation.completed_meals_served is not None else None,
        "assigned_ngo_id": donation.assigned_ngo_id,
    }
    return row


def _ensure_ml_training_table(client: bigquery.Client, settings) -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with _TABLE_LOCK:
        if _TABLE_READY:
            return
        project = settings.google_cloud_project
        dataset_id = settings.bigquery_ml_dataset
        table_id = settings.bigquery_ml_table
        dataset_ref = f"{project}.{dataset_id}"

        try:
            client.get_dataset(dataset_ref)
        except NotFound:
            ds = bigquery.Dataset(dataset_ref)
            ds.location = settings.gcp_region
            client.create_dataset(ds)

        schema = [
            bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("donation_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("donor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("donation_status", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("previous_status", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("food_type", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("quantity_kg", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("meal_count", "INT64", mode="NULLABLE"),
            bigquery.SchemaField("scan_passed", "BOOL", mode="NULLABLE"),
            bigquery.SchemaField("scan_confidence", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("scan_fallback_used", "BOOL", mode="NULLABLE"),
            bigquery.SchemaField("scan_model_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("scan_model_version", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("accuracy_score", "FLOAT64", mode="NULLABLE"),
            bigquery.SchemaField("accuracy_band", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("accuracy_recommendation", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("accuracy_fallback_used", "BOOL", mode="NULLABLE"),
            bigquery.SchemaField("accuracy_model_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("accuracy_model_version", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("scan_contract_version", "INT64", mode="NULLABLE"),
            bigquery.SchemaField("terminal_label", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("meals_served", "INT64", mode="NULLABLE"),
            bigquery.SchemaField("assigned_ngo_id", "STRING", mode="NULLABLE"),
        ]

        table_ref_full = f"{dataset_ref}.{table_id}"
        try:
            client.get_table(table_ref_full)
        except NotFound:
            table = bigquery.Table(table_ref_full, schema=schema)
            table.time_partitioning = bigquery.TimePartitioning(field="ingested_at")
            table.clustering_fields = ["donation_id", "event_type"]
            client.create_table(table)

        _TABLE_READY = True


def _record_ml_export_success() -> None:
    global _ml_export_succeeded, _ml_last_error, _ml_last_success_at
    with _METRICS_LOCK:
        _ml_export_succeeded += 1
        _ml_last_error = None
        _ml_last_success_at = datetime.now(timezone.utc)


def _record_ml_export_failure(message: str, donation_id: str | None = None) -> None:
    global _ml_export_failed, _ml_last_error, _ml_last_failure_at
    with _METRICS_LOCK:
        _ml_export_failed += 1
        _ml_last_error = message[:2000]
        _ml_last_failure_at = datetime.now(timezone.utc)
    try:
        from app.services.log_service import log_event

        log_event(
            event_type="ml_bigquery_export_failed",
            actor_id=None,
            donation_id=donation_id,
            status=None,
            payload={"error": message[:1500]},
        )
    except Exception:
        pass


def get_ml_export_metrics() -> dict[str, Any]:
    with _METRICS_LOCK:
        return {
            "rows_attempted": _ml_export_attempted,
            "rows_succeeded": _ml_export_succeeded,
            "rows_failed": _ml_export_failed,
            "last_error": _ml_last_error,
            "last_success_at": _iso_utc(_ml_last_success_at),
            "last_failure_at": _iso_utc(_ml_last_failure_at),
        }


def export_donation_ml_event(
    donation: Donation,
    event_type: str,
    *,
    previous_status: str | None = None,
    terminal_label: str | None = None,
) -> None:
    """Stream one row to BigQuery when enabled."""
    global _ml_export_attempted
    try:
        settings = get_settings()
        if not settings.ml_export_bigquery_enabled:
            return
        with _METRICS_LOCK:
            _ml_export_attempted += 1
        client = get_bigquery_client()
        _ensure_ml_training_table(client, settings)
        row = donation_event_to_row(
            donation,
            event_type,
            previous_status=previous_status,
            terminal_label=terminal_label,
        )
        table_ref = f"{settings.google_cloud_project}.{settings.bigquery_ml_dataset}.{settings.bigquery_ml_table}"
        errors = client.insert_rows_json(table_ref, [row])
        if errors:
            msg = f"insert_rows_json: {errors}"
            print(f"[ml_training_export] BigQuery {msg}")
            _record_ml_export_failure(msg, donation.id)
            return
        _record_ml_export_success()
    except Exception as exc:
        print(f"[ml_training_export] skipped: {exc}")
        _record_ml_export_failure(str(exc), donation.id)


def terminal_statuses() -> frozenset[str]:
    return _TERMINAL_STATUSES
