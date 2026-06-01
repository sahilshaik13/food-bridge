"""
Pull subscriber for `foodbridge-donations` — runs NGO ranking for events with
`matching_deferred: true` (see `DemoStore.create_donation`).

Run in production with:
  PUBSUB_MATCHING_ENABLED=true
  PUBSUB_MATCHING_INLINE_COMPLETION=false

Prereq: `python scripts/init_pubsub.py` (creates topic + `foodbridge-donations-matching-sub`).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "backend"))

from google.cloud import pubsub_v1  # noqa: E402

from app.core.cloud_clients import get_google_credentials  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.demo_store import store  # noqa: E402

SUBSCRIPTION = "foodbridge-donations-matching-sub"


def _handle(msg: Any) -> None:
    try:
        data = json.loads(msg.data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        msg.ack()
        return
    if data.get("event") != "donation_created":
        msg.ack()
        return
    if not data.get("matching_deferred"):
        msg.ack()
        return
    donation_id = data.get("donation_id")
    if not donation_id:
        msg.ack()
        return
    try:
        store.run_matching_for_donation(donation_id)
    except Exception as exc:  # noqa: BLE001
        print(f"run_matching_for_donation({donation_id}): {exc}")
        msg.nack()
        return
    msg.ack()


def main() -> None:
    settings = get_settings()
    if not settings.google_cloud_project:
        print("GOOGLE_CLOUD_PROJECT not set; exiting.")
        raise SystemExit(1)
    sub_path = f"projects/{settings.google_cloud_project}/subscriptions/{SUBSCRIPTION}"
    subscriber = pubsub_v1.SubscriberClient(credentials=get_google_credentials())
    print(f"Listening on {sub_path} — Ctrl+C to stop")
    streaming = subscriber.subscribe(sub_path, callback=_handle)
    try:
        streaming.result()
    except KeyboardInterrupt:
        streaming.cancel()
        print("Stopped.")


if __name__ == "__main__":
    main()
